package heapviz;

import java.io.IOException;
import java.nio.file.Paths;
import java.util.*;

import soot.*;
import soot.jimple.spark.pag.AllocNode;
import soot.jimple.spark.pag.PAG;
import soot.jimple.toolkits.callgraph.CallGraph;
import soot.jimple.toolkits.callgraph.Edge;
import soot.jimple.toolkits.callgraph.ReachableMethods;
import soot.options.Options;

/**
 * Static ownership tree orchestrator.
 * Constructs the points-to graph, runs dominator analysis, and classifies allocation site regions.
 */
public class OwnershipTree {

	static final long TOP = 1L << 63;

	final PAG pag;
	final CallGraph cg;
	final ReachableMethods rm;
	final String outDir, name;

	// node numbering: 0 ROOT, 1 GLOBAL, then methods, then sites
	final List<SootMethod> methods = new ArrayList<>();
	final Map<SootMethod, Integer> methodId = new HashMap<>();
	final List<AllocNode> sites = new ArrayList<>();
	final Map<AllocNode, Integer> siteId = new HashMap<>();
	final IdentityHashMap<Object, AllocNode> byNewExpr = new IdentityHashMap<>();
	final Set<SootMethod> entries = new HashSet<>();
	final Map<SootMethod, Long> retParams = new HashMap<>();

	int nNodes;
	int siteBase;

	int[] sccOf; // Strongly Connected Component
	boolean[] sccRecursive;
	List<int[]> sccSucc;

	final ReturnAnalysis returnAnalysis;
	final UnsafeStoreHandler unsafeStores;
	final StaticFieldLiveness staticLiveness;
	final HeapPartition heapPartition;
	final GraphBuilder builder;
	final SiteNaming naming;
	final OutputWriter writer;

	/**
	 * Constructs an OwnershipTree analysis instance.
	 *
	 * @param pag the Points-to Analysis Graph
	 * @param outDir directory for output files
	 * @param name base benchmark name
	 */
	OwnershipTree(PAG pag, String outDir, String name) {
		this.pag = pag;
		this.cg = Scene.v().getCallGraph();
		this.rm = Scene.v().getReachableMethods();
		this.outDir = outDir;
		this.name = name;
		this.returnAnalysis = new ReturnAnalysis(this);
		this.unsafeStores = new UnsafeStoreHandler(this);
		this.staticLiveness = new StaticFieldLiveness(this);
		this.heapPartition = new HeapPartition(this);
		this.builder = new GraphBuilder(this);
		this.naming = new SiteNaming(this);
		this.writer = new OutputWriter(this);
	}

	public static void main(String[] args) throws IOException {
		boolean identity = Boolean.getBoolean("ownership.identityReturns"); // TODO: Where is this set?
		boolean geom = Boolean.getBoolean("ownership.geom");
		List<String> a = new ArrayList<>(Arrays.asList(new main.GetSootArgs().get(args))); // Disables merge-stringbuffer and strips all-reachable to preserve distinct call chains.
		for (int i = 0; i + 1 < a.size(); i++) {
			if (a.get(i).equals("-output-format")) a.set(i + 1, "none");
			if (a.get(i).equals("-p") && a.get(i + 1).equals("cg") && i + 2 < a.size()
					&& a.get(i + 2).equals("all-reachable")) {
				a.remove(i); a.remove(i); a.remove(i); i--;
				continue;
			}
			if (a.get(i).equals("-p") && a.get(i + 1).equals("cg.spark") && i + 2 < a.size()
					&& a.get(i + 2).equals("on"))
				a.set(i + 2, "enabled:true,merge-stringbuffer:false" + (geom ? ",geom-pta:true,geom-trans:true" : ""));
		}
		System.out.println("[ownership] soot args: " + String.join(" ", a));
		Options.v().parse(a.toArray(new String[0]));
		Scene.v().loadNecessaryClasses();
		Scene.v().loadDynamicClasses();
		Scene.v().setEntryPoints(Scene.v().getEntryPoints());
		long t0 = System.currentTimeMillis();
		PackManager.v().getPack("wjpp").apply(); // Whole-Jimple Preprocessing Pack
		PackManager.v().getPack("cg").apply(); // Call Graph Pack
		System.out.println("[ownership] spark done in " + (System.currentTimeMillis() - t0) / 1000.0 + " s, "
				+ Scene.v().getReachableMethods().size() + " reachable methods");
		boolean inline = Boolean.getBoolean("ownership.inlineLib");
		if (identity) {
			int n = IdentityReturns.rewriteAll(Scene.v().getCallGraph(), Scene.v().getReachableMethods());
			System.out.println("[ownership] identity returns: " + n + " calls rewritten");
		}
		int depth = inline ? Integer.getInteger("ownership.inlineDepth", 3) : 0;
		boolean pending = identity;
		Set<SootMethod> reachBefore = null;
		for (int round = 0; round <= depth; round++) {
			if (pending) {
				G.v().MethodPAG_methodToPag.clear();
				Scene.v().releaseCallGraph();
				Scene.v().releasePointsToAnalysis();
				Scene.v().releaseReachableMethods();
				long t1 = System.currentTimeMillis();
				PackManager.v().getPack("cg").apply();
				System.out.println("[ownership] spark re-run done in " + (System.currentTimeMillis() - t1) / 1000.0
						+ " s, " + Scene.v().getReachableMethods().size() + " reachable methods");
				pending = false;
			}
			if (round == 0 && inline) {
				reachBefore = new HashSet<>();
				for (Iterator<MethodOrMethodContext> it = Scene.v().getReachableMethods().listener(); it.hasNext(); )
					reachBefore.add(it.next().method());
			}
			if (round == depth) break;
			int n = LibraryInliner.inlineRound(Scene.v().getCallGraph(), Scene.v().getReachableMethods(),
					Integer.getInteger("ownership.inlineUnits", 60), depth, round);
			if (n == 0) break;
			pending = true;
		}
		if (reachBefore != null) { // Checks reachable methods before vs. after inlining to guarantee no application methods were accidentally severed.
			Set<SootMethod> after = new HashSet<>();
			for (Iterator<MethodOrMethodContext> it = Scene.v().getReachableMethods().listener(); it.hasNext(); )
				after.add(it.next().method());
			int jdk = 0;
			List<String> app = new ArrayList<>();
			for (SootMethod m : reachBefore) {
				if (after.contains(m) || LibraryInliner.inlinedTargets.contains(m)) continue;
				if (LibraryInliner.isJdk(m)) jdk++;
				else app.add(m.getSignature());
			}
			Collections.sort(app);
			System.out.println("[ownership] reachability check: " + app.size() + " application and " + jdk
					+ " JDK methods reachable before inlining are not after (inlined methods excluded)"
					+ (app.isEmpty() ? "" : "; first: " + app.subList(0, Math.min(5, app.size()))));
		}
		PointsToAnalysis pta = Scene.v().getPointsToAnalysis();
		if (!(pta instanceof PAG)) {
			System.out.println("[ownership] points-to analysis is " + pta.getClass().getName() + ", not Spark");
			return;
		}
		String name = Paths.get(args[2]).getFileName().toString() + (identity ? "-id" : "") + (geom ? "-geom" : "")
				+ (inline ? "-inl" : "");
		new OwnershipTree((PAG) pta, args[4], name).run();
	}

	/** Numbers methods and allocation nodes, and finds entry points. */
	void number() {
		for (Iterator<MethodOrMethodContext> it = rm.listener(); it.hasNext(); ) {
			SootMethod m = it.next().method();
			if (!methodId.containsKey(m)) {
				methodId.put(m, methods.size());
				methods.add(m);
			}
		}
		for (AllocNode an : pag.getAllocNodeNumberer()) {
			if (an == null || siteId.containsKey(an)) continue;
			siteId.put(an, sites.size());
			sites.add(an);
			byNewExpr.put(an.getNewExpr(), an);
		}
		siteBase = 2 + methods.size();
		nNodes = siteBase + sites.size();
		for (SootMethod ep : Scene.v().getEntryPoints()) if (methodId.containsKey(ep)) entries.add(ep);
	}

	/** Returns node ID for a method. */
	int mNode(SootMethod m) { return 2 + methodId.get(m); }

	/** Returns node ID for an allocation node. */
	int sNode(AllocNode an) { return siteBase + siteId.get(an); }

	/** Computes dominators on the given graph and classifies allocation sites. */
	OwnershipResult classify(OwnershipGraph g, String label) {
		g.freeze(); // Freezes the edge list into a CSR (Compressed Sparse Row) representation for fast traversal.
		long t0 = System.currentTimeMillis();
		int[] idom = Dominators.dominators(nNodes, g.offsets, g.adjacency);
		OwnershipResult r = new OwnershipResult();
		r.idom = idom;
		int ns = sites.size();
		r.cls = new String[ns]; r.region = new String[ns]; r.owner = new String[ns];
		r.up = new int[ns]; r.rec = new boolean[ns];
		Map<Integer, List<Integer>> byRegion = new HashMap<>();
		for (int i = 0; i < ns; i++) {
			int v = siteBase + i;
			AllocNode an = sites.get(i);
			if (idom[v] == -1) { r.cls[i] = "UNREACHED"; r.region[i] = "-"; r.owner[i] = "-"; r.up[i] = -1; continue; }
			int o = idom[v];
			r.owner[i] = o == 0 ? "ROOT" : o == 1 ? "GLOBAL" : o < siteBase ? "FRAME" : "OBJECT";
			int x = o;
			while (x >= siteBase) x = idom[x];
			if (x < 2 || an.getMethod() == null) {
				r.cls[i] = "HEAP"; r.region[i] = x == 1 ? "GLOBAL" : "ROOT"; r.up[i] = -1;
				continue;
			}
			SootMethod rm = methods.get(x - 2);
			r.region[i] = rm.toString();
			r.rec[i] = sccRecursive[sccOf[methodId.get(rm)]];
			if (rm.equals(an.getMethod())) { r.cls[i] = "OWN"; r.up[i] = 0; }
			else { r.cls[i] = "UP"; byRegion.computeIfAbsent(x - 2, k -> new ArrayList<>()).add(i); }
		}
		for (Map.Entry<Integer, List<Integer>> en : byRegion.entrySet()) {
			int[] dist = bfsFrom(sccOf[en.getKey()]);
			for (int i : en.getValue()) {
				Integer am = methodId.get(sites.get(i).getMethod());
				r.up[i] = am == null ? -1 : dist[sccOf[am]];
			}
		}
		System.out.println("[ownership] graph " + label + ": " + nNodes + " nodes, " + g.edges + " edges, dominators in "
				+ (System.currentTimeMillis() - t0) / 1000.0 + " s");
		int want = Integer.getInteger("ownership.check", 40), checked = 0, bad = 0;
		for (int i = 0; i < ns && checked < want; i++) {
			if (!SiteNaming.isApp(sites.get(i)) || idom[siteBase + i] < 0) continue;
			checked++;
			if (!Dominators.dominates(nNodes, g.offsets, g.adjacency, idom[siteBase + i], siteBase + i)) {
				bad++;
				System.out.println("[ownership] CHECK FAILED: " + naming.nodeName(idom[siteBase + i]) + " does not dominate "
						+ naming.nodeName(siteBase + i));
			}
		}
		System.out.println("[ownership] check " + label + ": " + checked + " application sites, " + bad + " failures");
		String ex = System.getProperty("ownership.explain");
		if (ex != null) {
			for (int i = 0; i < ns; i++) {
				AllocNode an = sites.get(i);
				if (an.getMethod() == null || !naming.siteName(an).contains(ex)) continue;
				int[] p = Dominators.witness(nNodes, g.offsets, g.adjacency, mNode(an.getMethod()), siteBase + i);
				StringBuilder sb = new StringBuilder("[ownership] explain " + label + " " + naming.siteName(an) + ":");
				if (p == null) sb.append(" every path passes the allocating method");
				else for (int v : p) sb.append("\n      ").append(naming.nodeName(v));
				System.out.println(sb);
			}
		}
		return r;
	}

	/** Computes strongly connected components in the call graph using Tarjan's algorithm. */
	void methodSccs() {
		int n = methods.size();
		List<Set<Integer>> succ = new ArrayList<>();
		for (int i = 0; i < n; i++) succ.add(new HashSet<>());
		boolean[] selfLoop = new boolean[n];
		for (SootMethod m : methods) {
			int a = methodId.get(m);
			for (Iterator<Edge> it = cg.edgesOutOf(m); it.hasNext(); ) {
				Edge e = it.next();
				Integer b = methodId.get(e.tgt());
				if (b == null || GraphBuilder.async(e.kind())) continue;
				if (a == b) selfLoop[a] = true; else succ.get(a).add(b);
			}
		}
		int[] index = new int[n], low = new int[n];
		Arrays.fill(index, -1);
		boolean[] onStack = new boolean[n];
		int[] stk = new int[n];
		int sp = 0, idx = 0;
		sccOf = new int[n];
		List<Integer> sizes = new ArrayList<>();
		int[][] adj = new int[n][];
		for (int i = 0; i < n; i++) adj[i] = succ.get(i).stream().mapToInt(Integer::intValue).toArray();
		int[] cs = new int[n], ci = new int[n];
		for (int s = 0; s < n; s++) {
			if (index[s] != -1) continue;
			int csp = 0;
			cs[csp] = s; ci[csp++] = 0;
			index[s] = low[s] = idx++; stk[sp++] = s; onStack[s] = true;
			while (csp > 0) {
				int v = cs[csp - 1];
				if (ci[csp - 1] < adj[v].length) {
					int w = adj[v][ci[csp - 1]++];
					if (index[w] == -1) {
						index[w] = low[w] = idx++; stk[sp++] = w; onStack[w] = true;
						cs[csp] = w; ci[csp++] = 0;
					} else if (onStack[w]) low[v] = Math.min(low[v], index[w]);
				} else {
					csp--;
					if (csp > 0) { int u = cs[csp - 1]; low[u] = Math.min(low[u], low[v]); }
					if (low[v] == index[v]) {
						int size = 0, id = sizes.size();
						int w;
						do { w = stk[--sp]; onStack[w] = false; sccOf[w] = id; size++; } while (w != v);
						sizes.add(size);
					}
				}
			}
		}
		sccRecursive = new boolean[sizes.size()];
		for (int i = 0; i < n; i++) if (sizes.get(sccOf[i]) > 1 || selfLoop[i]) sccRecursive[sccOf[i]] = true;
		List<Set<Integer>> cs2 = new ArrayList<>();
		for (int i = 0; i < sizes.size(); i++) cs2.add(new HashSet<>());
		for (int a = 0; a < n; a++) for (int b : adj[a]) if (sccOf[a] != sccOf[b]) cs2.get(sccOf[a]).add(sccOf[b]);
		sccSucc = new ArrayList<>();
		for (Set<Integer> s : cs2) sccSucc.add(s.stream().mapToInt(Integer::intValue).toArray());
	}

	/** Computes BFS shortest path distances from a root SCC in the SCC DAG. */
	int[] bfsFrom(int scc) {
		int[] dist = new int[sccSucc.size()];
		Arrays.fill(dist, -1);
		int[] q = new int[dist.length];
		int h = 0, t = 0;
		q[t++] = scc; dist[scc] = 0;
		while (h < t) {
			int v = q[h++];
			for (int w : sccSucc.get(v)) if (dist[w] == -1) { dist[w] = dist[v] + 1; q[t++] = w; }
		}
		return dist;
	}

	/** Orchestrates the full ownership tree analysis. */
	void run() throws IOException {
		number();
		unsafeStores.findUnsafeStores();
		System.out.println("[ownership] " + unsafeStores.unsafeUnits.size() + " Unsafe object stores modelled as heap edges");
		returnAnalysis.computeReturns();
		methodSccs();
		boolean scopeLca = Boolean.parseBoolean(System.getProperty("ownership.scopeLca", "true"));
		if (scopeLca) staticLiveness.findStaticLifetimes();
		OwnershipGraph gb = new OwnershipGraph(this);
		builder.common(gb);
		System.out.println("[ownership] " + entries.size() + " entry points, " + builder.asyncEntries.size()
				+ " async targets" + (builder.asyncEntries.size() <= 40 ? ": " + builder.asyncTargets.keySet() : ""));
		builder.borrowFrames(gb);
		System.out.println("[ownership] frame edges B: " + builder.newEdges + " allocations, " + builder.callEdgesKept
				+ " calls kept, " + builder.callEdgesDropped + " calls dropped as parameter-derived, " + builder.caughtEdges
				+ " catch handlers (" + builder.caughtKept + " thrown sites kept, " + builder.caughtDropped
				+ " dropped as never thrown below the handler), " + builder.fallbacks
				+ " fell back to the local's points-to set; " + builder.unknownCalls
				+ " calls to bodiless methods that may keep their arguments");
		String[] names = new String[sites.size()];
		for (int i = 0; i < sites.size(); i++) names[i] = naming.siteName(sites.get(i));
		Integer[] ord = new Integer[sites.size()];
		for (int i = 0; i < ord.length; i++) ord[i] = i;
		Arrays.sort(ord, Comparator.comparing(i -> names[i]));

		OwnershipResult b = classify(gb, "B");
		writer.attribute(gb, b, ord, names);
		gb = null;
		OwnershipGraph gn = new OwnershipGraph(this);
		builder.common(gn);
		builder.naiveFrames(gn);
		OwnershipResult nv = classify(gn, "N");

		writer.writeOwn(b, nv, ord, names);
		writer.writeTree(b, ord, names);
		writer.summary("B", b);
		heapPartition.partition(b);
		heapPartition.printSummary();
		heapPartition.writePartitionFile(names);
		writer.summary("N", nv);
		if (Boolean.getBoolean("ownership.whatif")) writer.whatIf(b, ord, names);
	}
}
