package heapviz;

import java.io.BufferedWriter;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Paths;
import java.util.*;

import soot.*;
import soot.jimple.*;
import soot.jimple.spark.pag.AllocDotField;
import soot.jimple.spark.pag.AllocNode;
import soot.jimple.spark.pag.GlobalVarNode;
import soot.jimple.spark.pag.LocalVarNode;
import soot.jimple.spark.pag.Node;
import soot.jimple.spark.pag.PAG;
import soot.jimple.spark.pag.Parm;
import soot.jimple.spark.pag.VarNode;
import soot.jimple.spark.sets.P2SetVisitor;
import soot.jimple.spark.sets.PointsToSetInternal;
import soot.jimple.toolkits.callgraph.CallGraph;
import soot.jimple.toolkits.callgraph.Edge;
import soot.jimple.toolkits.callgraph.ReachableMethods;
import soot.options.Options;
import soot.tagkit.BytecodeOffsetTag;
import soot.toolkits.scalar.Pair;

/*
 * Static ownership tree, v0. 02-Current-Work/01-Design/2026-09-24-Ownership-Trees.md §5.
 *
 * Runs Soot and Spark with the arguments Stava would use (main.GetSootArgs), then builds one
 * graph and takes its dominator tree:
 *
 *   ROOT -> GLOBAL                     GLOBAL -> every object a static field may hold
 *   ROOT -> entry method               Scene entry points (main, JVM-called methods)
 *   ROOT -> async target               targets of THREAD, EXECUTOR, ASYNCTASK, FINALIZE edges
 *   m -> n                             every other call edge: frames are chained, caller first
 *   m -> site                          a reference the frame of m obtains itself (see below)
 *   site -> site                       Spark's field and array-element points-to sets
 *   GLOBAL -> site                     Spark's special nodes, string and class constants, and
 *                                      the parameters of entry and async methods
 *
 * Which definitions give a frame edge is the borrow rule (graph B):
 *   x = new ...                        yes
 *   x = call(...)                      only if some target may return an object not derived
 *                                      from its own parameters (retParams below)
 *   x := @caughtexception              yes
 *   x := @this, @parameter             no: an older frame on the same stack holds the object
 *   x = y, (T) y, y.f, y[i]            no: the object is reachable from y's object, which this
 *                                      frame or an older one holds
 *   x = C.f, constants                 no: GLOBAL already reaches them
 * Graph N gives every local of m an edge to its whole points-to set, as a baseline.
 *
 * A site's region is the nearest method above it in the dominator tree. If that is the
 * allocating method the site is OWN, if another method UP, otherwise HEAP. The claim is that
 * every object of the site dies no later than the oldest activation of the region method on
 * its thread returns (design note, lemmas A-C).
 *
 * System properties:
 *   ownership.identityReturns=true     rewrite x = y.m(..) to y.m(..); x = y when every target
 *                                      returns exactly that argument, then run Spark again
 *   ownership.check=N                  check that idom(site) really dominates, for N sites
 *
 * Output: <outdir>/<name>.own (one line per allocation site) and <name>.owntree (the dominator
 * chain of every application site, for reading by hand).
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
	final Set<SootMethod> entries = new HashSet<>(), asyncEntries = new HashSet<>();
	final Map<SootMethod, Long> retParams = new HashMap<>();

	int nNodes;
	int siteBase;

	OwnershipTree(PAG pag, String outDir, String name) {
		this.pag = pag;
		this.cg = Scene.v().getCallGraph();
		this.rm = Scene.v().getReachableMethods();
		this.outDir = outDir;
		this.name = name;
	}

	public static void main(String[] args) throws IOException {
		boolean identity = Boolean.getBoolean("ownership.identityReturns");
		// ownership.geom: Soot's geometric-encoding refinement of Spark (context-sensitive for
		// pointers and heap, encoding Geom), written back into Spark's points-to sets
		// (geom-trans) so that everything below reads the refined heap unchanged.
		boolean geom = Boolean.getBoolean("ownership.geom");
		List<String> a = new ArrayList<>(Arrays.asList(new main.GetSootArgs().get(args)));
		for (int i = 0; i + 1 < a.size(); i++) {
			if (a.get(i).equals("-output-format")) a.set(i + 1, "none");
			// Stava's non-benchmark arguments make every application method an entry point;
			// that would cut every frame chain at the root, so only main is kept.
			if (a.get(i).equals("-p") && a.get(i + 1).equals("cg") && i + 2 < a.size()
					&& a.get(i + 2).equals("all-reachable")) {
				a.remove(i); a.remove(i); a.remove(i); i--;
				continue;
			}
			// Spark merges every StringBuffer/StringBuilder into one node by default, which
			// would make every builder site the same object.
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
		PackManager.v().getPack("wjpp").apply();
		PackManager.v().getPack("cg").apply();
		System.out.println("[ownership] spark done in " + (System.currentTimeMillis() - t0) / 1000.0 + " s, "
				+ Scene.v().getReachableMethods().size() + " reachable methods");
		boolean inline = Boolean.getBoolean("ownership.inlineLib");
		if (identity) {
			int n = IdentityReturns.rewriteAll(Scene.v().getCallGraph(), Scene.v().getReachableMethods());
			System.out.println("[ownership] identity returns: " + n + " calls rewritten");
		}
		int depth = inline ? Integer.getInteger("ownership.inlineDepth", 3) : 0;
		boolean pending = identity;       // code changed since the last Spark run
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
			// each round resolves its copied calls against the Spark run that followed the last one
			int n = LibraryInliner.inlineRound(Scene.v().getCallGraph(), Scene.v().getReachableMethods(),
					Integer.getInteger("ownership.inlineUnits", 60), depth, round);
			if (n == 0) break;
			pending = true;
		}
		if (reachBefore != null) {
			// Self-check: inlining copies JDK bodies and must not cut a call chain. Methods that
			// were reachable before and are not after, other than the inlined JDK methods
			// themselves, are either spurious targets a copy resolved away or a broken edge; an
			// application method among them is almost always the second.
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

	// ------------------------------------------------------------------ numbering

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

	int mNode(SootMethod m) { return 2 + methodId.get(m); }
	int sNode(AllocNode an) { return siteBase + siteId.get(an); }

	static boolean async(Kind k) {
		return k.isThread() || k.isExecutor() || k.isAsyncTask() || k == Kind.FINALIZE
				|| k == Kind.INVOKE_FINALIZE || k == Kind.HANDLER;
	}

	/**
	 * Soot adds a FINALIZE edge from every allocation of a class to its finalize(), including
	 * Object's empty one. An empty finalizer holds nothing, and treating its receiver as held by
	 * another thread would put every object in the program under GLOBAL. A finalizer with a body
	 * does keep its object (it may resurrect it), so that one stays an async entry.
	 */
	static boolean emptyFinalizer(Edge e) {
		if (e.kind() != Kind.FINALIZE && e.kind() != Kind.INVOKE_FINALIZE) return false;
		SootMethod t = e.tgt();
		if (t.getDeclaringClass().getName().equals("java.lang.Object")) return true;
		if (!t.hasActiveBody()) return false;
		for (Unit u : t.getActiveBody().getUnits())
			if (!(u instanceof IdentityStmt) && !(u instanceof ReturnVoidStmt)) return false;
		return true;
	}

	final Map<String, Integer> asyncTargets = new TreeMap<>();

	// TODO: What are these Retaining Natives
	static final Set<String> RETAINING_JDK_NATIVES = new HashSet<>(Arrays.asList(
			"<java.lang.String: java.lang.String intern()>",
			"<java.lang.Thread: void start0()>"));

	// Unsafe's object stores write the value into a field of the first argument: a heap edge,
	// not a global one. Value argument index for each.
	// TODO: How is this used?
	static final Map<String, Integer> UNSAFE_STORES = new HashMap<>();
	static {
		UNSAFE_STORES.put("<sun.misc.Unsafe: void putObject(java.lang.Object,long,java.lang.Object)>", 2);
		UNSAFE_STORES.put("<sun.misc.Unsafe: void putObjectVolatile(java.lang.Object,long,java.lang.Object)>", 2);
		UNSAFE_STORES.put("<sun.misc.Unsafe: void putOrderedObject(java.lang.Object,long,java.lang.Object)>", 2);
		UNSAFE_STORES.put("<sun.misc.Unsafe: boolean compareAndSwapObject(java.lang.Object,long,java.lang.Object,java.lang.Object)>", 3);
		UNSAFE_STORES.put("<sun.misc.Unsafe: java.lang.Object getAndSetObject(java.lang.Object,long,java.lang.Object)>", 2);
	}

	/** A method without a body that may keep a reference to what it is passed. */
	static boolean retains(SootMethod t) {
		String c = t.getDeclaringClass().getName();
		boolean jdk = c.startsWith("java.") || c.startsWith("javax.") || c.startsWith("sun.")
				|| c.startsWith("com.sun.") || c.startsWith("jdk.");
		return !jdk || RETAINING_JDK_NATIVES.contains(t.getSignature());
	}

	// One node per Unsafe store call site: every object the call may write into points to it,
	// and it points to every value written. Linking the two sets directly would multiply them.
	final List<Unit> unsafeUnits = new ArrayList<>();
	final List<SootMethod> unsafeMethods = new ArrayList<>();
	int unsafeBase;

	void findUnsafeStores() {
		for (SootMethod m : methods) {
			if (!m.hasActiveBody()) continue;
			for (Unit u : m.getActiveBody().getUnits()) {
				if (!(u instanceof Stmt) || !((Stmt) u).containsInvokeExpr()) continue;
				for (Iterator<Edge> it = cg.edgesOutOf(u); it.hasNext(); )
					if (UNSAFE_STORES.containsKey(it.next().tgt().getSignature())) {
						unsafeUnits.add(u);
						unsafeMethods.add(m);
						break;
					}
			}
		}
		unsafeBase = siteBase + sites.size();
		nNodes = unsafeBase + unsafeUnits.size();
	}

	void unsafeEdges(Graph g) {
		for (int k = 0; k < unsafeUnits.size(); k++) {
			InvokeExpr ie = ((Stmt) unsafeUnits.get(k)).getInvokeExpr();
			int node = unsafeBase + k;
			Integer vi = null;
			for (Iterator<Edge> it = cg.edgesOutOf(unsafeUnits.get(k)); it.hasNext(); ) {
				Integer x = UNSAFE_STORES.get(it.next().tgt().getSignature());
				if (x != null) vi = x;
			}
			if (vi == null || ie.getArgCount() <= vi) continue;
			Value o = ie.getArg(0), v = ie.getArg(vi);
			if (!(o instanceof Local) || !(v instanceof Local)) continue;
			PointsToSet po = pag.reachingObjects((Local) o);
			if (po instanceof PointsToSetInternal)
				((PointsToSetInternal) po).forall(new P2SetVisitor() {
					@Override public void visit(Node n) {
						if (n instanceof AllocNode && siteId.containsKey(n)) g.edge(sNode((AllocNode) n), node);
					}
				});
			g.toSites(node, pag.reachingObjects((Local) v));
		}
	}

	int unknownCalls;

	// ------------------------------------------------------------------ return analysis

	static long bit(int k) { return 1L << k; }       // 0 = this, k + 1 = parameter k

	/** Which parameters a call's result may derive from, TOP if it may be something else. */
	// TODO: The fuck is happening here?
	long callValue(Unit u, InvokeExpr ie, Map<Local, Long> d) {
		Iterator<Edge> it = cg.edgesOutOf(u);
		if (!it.hasNext()) return TOP;
		long r = 0;
		while (it.hasNext()) {
			Edge e = it.next();
			if (e.kind() == Kind.CLINIT) continue; // Implicit call to static initializer. https://www.sable.mcgill.ca/soot/doc/soot/Kind.html
			if (!e.kind().isExplicit()) return TOP; // isExplicit: the call is due to an explicit invoke statement
			Long rp = retParams.get(e.tgt());
			if (rp == null || (rp & TOP) != 0) return TOP;
			for (int k = 0; k < 63; k++) {
				if ((rp & bit(k)) == 0) continue;
				Value v;
				if (k == 0) {
					if (!(ie instanceof InstanceInvokeExpr)) return TOP;
					v = ((InstanceInvokeExpr) ie).getBase();
				} else {
					if (k - 1 >= ie.getArgCount()) return TOP;
					v = ie.getArg(k - 1);
				}
				r |= valueOf(v, d);
			}
		}
		return r;
	}

	static long valueOf(Value v, Map<Local, Long> d) {
		if (v instanceof Local) return d.getOrDefault(v, 0L);
		if (v instanceof NullConstant) return 0;
		return TOP;
	}

	/** Parameter derivation of every local of m: flow-insensitive, least fixpoint. */
	Map<Local, Long> derive(SootMethod m) {
		Map<Local, Long> d = new HashMap<>();
		Body b = m.getActiveBody();
		boolean changed = true;
		while (changed) {
			changed = false;
			for (Unit u : b.getUnits()) {
				Local lhs;
				long v;
				if (u instanceof IdentityStmt) {
					IdentityStmt is = (IdentityStmt) u;
					if (!(is.getLeftOp() instanceof Local)) continue;
					lhs = (Local) is.getLeftOp();
					Value r = is.getRightOp();
					if (r instanceof ThisRef) v = bit(0);
					else if (r instanceof ParameterRef) v = bit(((ParameterRef) r).getIndex() + 1);
					else v = TOP;
				} else if (u instanceof AssignStmt) {
					AssignStmt as = (AssignStmt) u;
					if (!(as.getLeftOp() instanceof Local)) continue;
					lhs = (Local) as.getLeftOp();
					if (!(lhs.getType() instanceof RefLikeType)) continue;
					Value r = as.getRightOp();
					if (r instanceof Local) v = d.getOrDefault(r, 0L);
					else if (r instanceof CastExpr) v = valueOf(((CastExpr) r).getOp(), d);
					else if (r instanceof InstanceFieldRef) v = valueOf(((InstanceFieldRef) r).getBase(), d);
					else if (r instanceof ArrayRef) v = valueOf(((ArrayRef) r).getBase(), d);
					else if (r instanceof InvokeExpr) v = callValue(u, (InvokeExpr) r, d);
					else if (r instanceof NullConstant) v = 0;
					else v = TOP;
				} else continue;
				long old = d.getOrDefault(lhs, 0L);
				if ((old | v) != old) {
					d.put(lhs, old | v);
					changed = true;
				}
			}
		}
		return d;
	}

	long returnsOf(SootMethod m, Map<Local, Long> d) {
		long r = 0;
		for (Unit u : m.getActiveBody().getUnits()) {
			if (!(u instanceof ReturnStmt)) continue;
			r |= valueOf(((ReturnStmt) u).getOp(), d);
		}
		return r;
	}

	void computeReturns() {
		Map<SootMethod, Set<SootMethod>> callers = new HashMap<>();
		Deque<SootMethod> work = new ArrayDeque<>();
		for (SootMethod m : methods) {
			if (!m.hasActiveBody()) { retParams.put(m, TOP); continue; }
			retParams.put(m, 0L);
			work.add(m);
			for (Iterator<Edge> it = cg.edgesOutOf(m); it.hasNext(); )
				callers.computeIfAbsent(it.next().tgt(), k -> new HashSet<>()).add(m);
		}
		Set<SootMethod> queued = new HashSet<>(work);
		int rounds = 0;
		while (!work.isEmpty()) {
			SootMethod m = work.poll();
			queued.remove(m);
			rounds++;
			long old = retParams.get(m);
			long r = returnsOf(m, derive(m));
			long nw = ((old | r) & TOP) != 0 ? TOP : (old | r);
			if (nw != old) {
				retParams.put(m, nw);
				for (SootMethod c : callers.getOrDefault(m, Collections.emptySet()))
					if (c.hasActiveBody() && queued.add(c)) work.add(c);
			}
		}
		int top = 0, param = 0, none = 0;
		for (long v : retParams.values()) { if ((v & TOP) != 0) top++; else if (v != 0) param++; else none++; }
		System.out.println("[ownership] returns: " + param + " methods return a parameter-derived value, "
				+ top + " may return something else, " + none + " return nothing; " + rounds + " method visits");
	}

	// ------------------------------------------------------------------ graph

	static final class IntList {
		int[] a = new int[1024];
		int n;
		void add(int x) { if (n == a.length) a = Arrays.copyOf(a, n * 2); a[n++] = x; }
	}

	final class Graph {
		IntList src = new IntList(), dst = new IntList();
		int edges;
		// Edges from one source usually arrive together (one method's locals, one site's
		// fields), so they are collected in a set and written once: graph N on the corpus had
		// 34 million edges before this, most of them repeats.
		final BitSet pending = new BitSet();
		int pendingSrc = -1;
		void flush() {
			for (int d = pending.nextSetBit(0); d >= 0; d = pending.nextSetBit(d + 1)) { src.add(pendingSrc); dst.add(d); }
			pending.clear();
		}
		void edge(int s, int d) {
			if (s != pendingSrc) { flush(); pendingSrc = s; }
			pending.set(d);
		}
		void toSites(int s, PointsToSet pts) {
			if (!(pts instanceof PointsToSetInternal)) return;
			((PointsToSetInternal) pts).forall(new P2SetVisitor() {
				@Override public void visit(Node n) {
					if (n instanceof AllocNode && siteId.containsKey(n)) edge(s, sNode((AllocNode) n));
				}
			});
		}
		int[] off, adj;
		void freeze() {
			flush();
			off = new int[nNodes + 1];
			for (int i = 0; i < src.n; i++) off[src.a[i] + 1]++;
			for (int i = 0; i < nNodes; i++) off[i + 1] += off[i];
			adj = new int[src.n];
			int[] pos = Arrays.copyOf(off, nNodes);
			for (int i = 0; i < src.n; i++) adj[pos[src.a[i]]++] = dst.a[i];
			edges = src.n;
			src = null; dst = null;
		}
	}

	int newEdges, callEdgesKept, callEdgesDropped, caughtEdges, fallbacks;

	// Why each node hangs directly off GLOBAL (first reason recorded), for the attribution of
	// HEAP sites: static:<field>, special:<node>, native-arg:<callee>, entry-param:<method>,
	// thread-param:<method>.
	final Map<Integer, String> globalWhy = new HashMap<>();

	void global(Graph g, String why, PointsToSet pts) {
		if (!(pts instanceof PointsToSetInternal)) return;
		((PointsToSetInternal) pts).forall(new P2SetVisitor() {
			@Override public void visit(Node n) {
				if (!(n instanceof AllocNode) || !siteId.containsKey(n)) return;
				int s = sNode((AllocNode) n);
				g.edge(1, s);
				globalWhy.putIfAbsent(s, why);
			}
		});
	}

	// What-if switches (ownership.whatif=true): not sound, they measure how much of HEAP is due to
	// one modelling source. specialSinks: Spark's @SPECIAL nodes (main's args array, the value
	// natives return, reflection placeholders) keep no fields, so nothing is reachable through
	// them. phantomNoop: calls to methods of classes Soot has no bytecode for (never loaded in
	// the Tamiflex run) keep nothing.
	boolean specialSinks, phantomNoop;

	static boolean isSpecial(AllocNode an) {
		return an.getMethod() == null && !isToken(an);
	}

	/** Edges every variant shares: root, calls, statics, special nodes, heap fields. */
	void common(Graph g) {
		// each graph records its own reasons; the what-if variants once reused graph B's, which
		// mislabelled their .ownwhy-sp (Micro-Corpus-Log F21.2)
		globalWhy.clear();
		g.edge(0, 1);
		for (SootMethod ep : entries) g.edge(0, mNode(ep));
		for (SootMethod m : methods) {
			for (Iterator<Edge> it = cg.edgesOutOf(m); it.hasNext(); ) {
				Edge e = it.next();
				if (!methodId.containsKey(e.tgt())) continue;
				if (emptyFinalizer(e)) continue;
				if (async(e.kind())) {
					g.edge(0, mNode(e.tgt()));
					if (asyncEntries.add(e.tgt())) asyncTargets.merge(e.kind() + " " + e.tgt(), 1, Integer::sum);
				} else g.edge(mNode(m), mNode(e.tgt()));
			}
		}
		for (AllocNode an : sites) {
			if (an.getMethod() == null || isToken(an)) {
				g.edge(1, sNode(an));
				globalWhy.putIfAbsent(sNode(an), "special:" + siteName(an));
			}
			if (specialSinks && isSpecial(an)) continue;
			for (AllocDotField f : an.getFields()) g.toSites(sNode(an), f.getP2Set());
		}
		unsafeEdges(g);
		for (VarNode v : pag.getVarNodeNumberer()) {
			if (v instanceof GlobalVarNode && v.getVariable() instanceof SootField)
				global(g, "static:" + ((SootField) v.getVariable()).getSignature(), v.getP2Set());
		}
		// a callee without a body may keep what it is given (corpus E04's native sink). JDK
		// natives are trusted to Spark's model, except those known to store a reference.
		for (SootMethod m : methods) {
			if (!m.hasActiveBody()) continue;
			for (Unit u : m.getActiveBody().getUnits()) {
				if (!(u instanceof Stmt) || !((Stmt) u).containsInvokeExpr()) continue;
				InvokeExpr ie = ((Stmt) u).getInvokeExpr();
				for (Iterator<Edge> it = cg.edgesOutOf(u); it.hasNext(); ) {
					SootMethod t = it.next().tgt();
					if (t.hasActiveBody() || !retains(t)) continue;
					if (phantomNoop && t.getDeclaringClass().isPhantom()) continue;
					unknownCalls++;
					String why = (t.getDeclaringClass().isPhantom() ? "phantom-arg:" : "native-arg:") + t.getSignature();
					if (ie instanceof InstanceInvokeExpr) global(g, why, pag.reachingObjects((Local) ((InstanceInvokeExpr) ie).getBase()));
					for (Value v : ie.getArgs())
						if (v instanceof Local && v.getType() instanceof RefLikeType) global(g, why, pag.reachingObjects((Local) v));
				}
			}
		}
		// the JVM holds the parameters of methods it calls, and of methods started on a thread
		for (SootMethod m : methods) {
			if (!m.hasActiveBody() || !(entries.contains(m) || asyncEntries.contains(m))) continue;
			for (Unit u : m.getActiveBody().getUnits()) {
				if (!(u instanceof IdentityStmt)) continue;
				IdentityStmt is = (IdentityStmt) u;
				if ((is.getRightOp() instanceof ThisRef || is.getRightOp() instanceof ParameterRef)
						&& is.getLeftOp() instanceof Local)
					global(g, (entries.contains(m) ? "entry-param:" : "thread-param:") + m.getSignature(),
							pag.reachingObjects((Local) is.getLeftOp()));
			}
		}
	}

	// Spark sends every thrown object through one global node, so any catch of a supertype
	// anywhere receives it. A handler frame is an ancestor of the frame that threw, so a
	// catch in h can only receive an object thrown by a method h reaches in the call graph.
	final Map<Integer, List<Integer>> throwers = new HashMap<>();   // site -> throwing methods
	final Map<Integer, BitSet> reachFrom = new HashMap<>();

	void collectThrowers() {
		for (SootMethod m : methods) {
			if (!m.hasActiveBody()) continue;
			int mi = methodId.get(m);
			for (Unit u : m.getActiveBody().getUnits()) {
				if (!(u instanceof ThrowStmt) || !(((ThrowStmt) u).getOp() instanceof Local)) continue;
				PointsToSet pts = pag.reachingObjects((Local) ((ThrowStmt) u).getOp());
				if (!(pts instanceof PointsToSetInternal)) continue;
				((PointsToSetInternal) pts).forall(new P2SetVisitor() {
					@Override public void visit(Node n) {
						Integer s = siteId.get(n);
						if (s != null) throwers.computeIfAbsent(s, k -> new ArrayList<>()).add(mi);
					}
				});
			}
		}
	}

	BitSet reach(int mi) {
		return reachFrom.computeIfAbsent(mi, k -> {
			BitSet seen = new BitSet();
			Deque<Integer> q = new ArrayDeque<>();
			q.add(k); seen.set(k);
			while (!q.isEmpty()) {
				SootMethod m = methods.get(q.poll());
				for (Iterator<Edge> it = cg.edgesOutOf(m); it.hasNext(); ) {
					Edge e = it.next();
					Integer t = methodId.get(e.tgt());
					if (t != null && !async(e.kind()) && !seen.get(t)) { seen.set(t); q.add(t); }
				}
			}
			return seen;
		});
	}

	int caughtKept, caughtDropped;

	void caughtEdges(Graph g, SootMethod h, Local l) {
		PointsToSet pts = pag.reachingObjects(l);
		if (!(pts instanceof PointsToSetInternal)) return;
		BitSet r = reach(methodId.get(h));
		int hn = mNode(h);
		((PointsToSetInternal) pts).forall(new P2SetVisitor() {
			@Override public void visit(Node n) {
				Integer s = siteId.get(n);
				if (s == null) return;
				boolean ok = false;
				for (int t : throwers.getOrDefault(s, Collections.emptyList())) if (r.get(t)) { ok = true; break; }
				if (ok) { g.edge(hn, siteBase + s); caughtKept++; } else caughtDropped++;
			}
		});
	}

	/** Graph B: frame edges under the borrow rule. */
	boolean throwersCollected;

	void borrowFrames(Graph g) {
		if (!throwersCollected) { collectThrowers(); throwersCollected = true; }
		for (SootMethod m : methods) {
			if (!m.hasActiveBody()) continue;
			int mn = mNode(m);
			Map<Local, Long> d = null;
			for (Unit u : m.getActiveBody().getUnits()) {
				if (u instanceof IdentityStmt) {
					IdentityStmt is = (IdentityStmt) u;
					if (is.getRightOp() instanceof CaughtExceptionRef && is.getLeftOp() instanceof Local) {
						caughtEdges(g, m, (Local) is.getLeftOp());
						caughtEdges++;
					}
					continue;
				}
				if (!(u instanceof AssignStmt)) continue;
				AssignStmt as = (AssignStmt) u;
				if (!(as.getLeftOp() instanceof Local) || !(as.getLeftOp().getType() instanceof RefLikeType)) continue;
				Local lhs = (Local) as.getLeftOp();
				Value r = as.getRightOp();
				if (r instanceof AnyNewExpr) {
					AllocNode an = byNewExpr.get(r);
					if (an != null && siteId.containsKey(an)) g.edge(mn, sNode(an));
					else { g.toSites(mn, pag.reachingObjects(lhs)); fallbacks++; }
					newEdges++;
				} else if (r instanceof InvokeExpr) {
					if (d == null) d = derive(m);
					if ((callValue(u, (InvokeExpr) r, d) & TOP) == 0) { callEdgesDropped++; continue; }
					callEdgesKept++;
					boolean fellBack = false;
					Iterator<Edge> it = cg.edgesOutOf(u);
					if (!it.hasNext()) fellBack = true;
					while (it.hasNext()) {
						Edge e = it.next();
						if (e.kind() == Kind.CLINIT) continue;
						Long rp = retParams.get(e.tgt());
						if (!e.kind().isExplicit() || rp == null || !e.tgt().hasActiveBody()) { fellBack = true; continue; }
						if ((rp & TOP) == 0) continue;
						LocalVarNode rn = pag.findLocalVarNode(Parm.v(e.tgt(), PointsToAnalysis.RETURN_NODE));
						if (rn == null) fellBack = true;
						else g.toSites(mn, rn.getP2Set());
					}
					if (fellBack) { g.toSites(mn, pag.reachingObjects(lhs)); fallbacks++; }
				}
			}
		}
	}

	/** Graph N: every local of m points at its whole points-to set. */
	void naiveFrames(Graph g) {
		for (SootMethod m : methods) {
			if (!m.hasActiveBody()) continue;
			int mn = mNode(m);
			for (Local l : m.getActiveBody().getLocals())
				if (l.getType() instanceof RefLikeType) g.toSites(mn, pag.reachingObjects(l));
		}
	}

	// ------------------------------------------------------------------ dominators

	/** Cooper, Harvey, Kennedy, "A Simple, Fast Dominance Algorithm" (2001). -1 = unreachable. */
	static int[] dominators(int n, int[] off, int[] adj) {
		int[] po = new int[n];
		Arrays.fill(po, -1);
		int[] order = new int[n];
		int cnt = 0;
		int[] stack = new int[n], it = new int[n];
		boolean[] seen = new boolean[n];
		int sp = 0;
		stack[sp++] = 0; seen[0] = true; it[0] = off[0];
		while (sp > 0) {
			int v = stack[sp - 1];
			if (it[v] < off[v + 1]) {
				int w = adj[it[v]++];
				if (!seen[w]) { seen[w] = true; it[w] = off[w]; stack[sp++] = w; }
			} else {
				sp--;
				po[v] = cnt;
				order[cnt++] = v;
			}
		}
		// predecessors among reachable nodes
		int[] poff = new int[n + 1];
		for (int v = 0; v < n; v++) if (po[v] >= 0) for (int i = off[v]; i < off[v + 1]; i++) poff[adj[i] + 1]++;
		for (int v = 0; v < n; v++) poff[v + 1] += poff[v];
		int[] padj = new int[poff[n]];
		int[] pos = Arrays.copyOf(poff, n);
		for (int v = 0; v < n; v++) if (po[v] >= 0) for (int i = off[v]; i < off[v + 1]; i++) padj[pos[adj[i]]++] = v;
		int[] idom = new int[n];
		Arrays.fill(idom, -1);
		idom[0] = 0;
		boolean changed = true;
		while (changed) {
			changed = false;
			for (int k = cnt - 1; k >= 0; k--) {           // reverse postorder
				int b = order[k];
				if (b == 0) continue;
				int nd = -1;
				for (int i = poff[b]; i < poff[b + 1]; i++) {
					int p = padj[i];
					if (idom[p] == -1) continue;
					if (nd == -1) { nd = p; continue; }
					int f1 = p, f2 = nd;
					while (f1 != f2) {
						while (po[f1] < po[f2]) f1 = idom[f1];
						while (po[f2] < po[f1]) f2 = idom[f2];
					}
					nd = f1;
				}
				if (idom[b] != nd) { idom[b] = nd; changed = true; }
			}
		}
		return idom;
	}

	/** True if every path from ROOT to target passes through d (BFS with d removed). */
	static boolean dominates(int n, int[] off, int[] adj, int d, int target) {
		if (d == target || d == 0) return true;
		boolean[] seen = new boolean[n];
		int[] q = new int[n];
		int h = 0, t = 0;
		q[t++] = 0; seen[0] = true; seen[d] = true;
		while (h < t) {
			int v = q[h++];
			if (v == target) return false;
			for (int i = off[v]; i < off[v + 1]; i++) if (!seen[adj[i]]) { seen[adj[i]] = true; q[t++] = adj[i]; }
		}
		return true;
	}

	/** A shortest path from ROOT to target that avoids node `avoid`, or null. */
	static int[] witness(int n, int[] off, int[] adj, int avoid, int target) {
		int[] parent = new int[n];
		Arrays.fill(parent, -2);
		int[] q = new int[n];
		int h = 0, t = 0;
		q[t++] = 0; parent[0] = -1;
		if (avoid >= 0) parent[avoid] = -3;
		while (h < t) {
			int v = q[h++];
			if (v == target) break;
			for (int i = off[v]; i < off[v + 1]; i++)
				if (parent[adj[i]] == -2) { parent[adj[i]] = v; q[t++] = adj[i]; }
		}
		if (parent[target] == -2 || parent[target] == -3) return null;
		List<Integer> p = new ArrayList<>();
		for (int v = target; v != -1; v = parent[v]) p.add(v);
		Collections.reverse(p);
		return p.stream().mapToInt(Integer::intValue).toArray();
	}

	// ------------------------------------------------------------------ call-graph SCCs and distance

	int[] sccOf;
	boolean[] sccRecursive;
	List<int[]> sccSucc;

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
				if (b == null || async(e.kind())) continue;
				if (a == b) selfLoop[a] = true; else succ.get(a).add(b);
			}
		}
		// Tarjan, iterative
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

	// ------------------------------------------------------------------ naming (as patch 0006)

	static boolean isToken(AllocNode an) {
		Object e = an.getNewExpr();
		if (e instanceof Pair) e = ((Pair<?, ?>) e).getO1();
		return e == PointsToAnalysis.STRING_NODE || e instanceof ClassConstant || e instanceof Type;
	}

	static Integer bciOf(Unit u) {
		for (ValueBox ub : u.getUseBoxes()) {
			if (!ub.getClass().toString().equals("class soot.jimple.internal.JAssignStmt$LinkedRValueBox"))
				continue;
			Value v = ub.getValue();
			if (!(v instanceof NewArrayExpr || v instanceof NewMultiArrayExpr)) continue;
			BytecodeOffsetTag tg = (BytecodeOffsetTag) ub.getTag("BytecodeOffsetTag");
			if (tg != null) return tg.getBytecodeOffset();
		}
		BytecodeOffsetTag t = (BytecodeOffsetTag) u.getTag("BytecodeOffsetTag");
		return t == null ? null : t.getBytecodeOffset();
	}

	final Map<SootMethod, IdentityHashMap<Object, Unit>> allocUnits = new HashMap<>();

	String siteName(AllocNode an) {
		Object e = an.getNewExpr();
		if (e instanceof Pair) e = ((Pair<?, ?>) e).getO1();
		SootMethod m = an.getMethod();
		if (e == PointsToAnalysis.STRING_NODE) return "@STRING";
		if (e instanceof ClassConstant) return "@CLASS:" + ((ClassConstant) e).getValue();
		if (e instanceof Type) return "@MERGED:" + e;
		if (m == null) return "@SPECIAL:" + e;
		IdentityHashMap<Object, Unit> r = allocUnits.computeIfAbsent(m, k -> {
			IdentityHashMap<Object, Unit> x = new IdentityHashMap<>();
			if (k.hasActiveBody())
				for (Unit u : k.getActiveBody().getUnits())
					if (u instanceof AssignStmt && ((AssignStmt) u).getRightOp() instanceof AnyNewExpr)
						x.put(((AssignStmt) u).getRightOp(), u);
			return x;
		});
		Unit u = r.get(e);
		Integer b = u == null ? null : bciOf(u);
		if (b == null) return "@NOUNIT:" + m;
		String ch = LibraryInliner.chain.get(u);       // an allocation brought in by library inlining
		return ch != null ? m + "#" + ch + "|" + b + "|" + an.getType() : m + "|" + b + "|" + an.getType();
	}

	String nodeName(int v) {
		if (v == 0) return "ROOT";
		if (v == 1) return "GLOBAL";
		if (v < siteBase) return "M:" + methods.get(v - 2);
		if (v >= unsafeBase) return "UNSAFE:" + unsafeMethods.get(v - unsafeBase);
		return "S:" + siteName(sites.get(v - siteBase));
	}

	// ------------------------------------------------------------------ run

	static final class Result {
		int[] idom;
		String[] cls, region, owner;
		int[] up;
		boolean[] rec;
	}

	Result classify(Graph g, String label) {
		g.freeze();
		long t0 = System.currentTimeMillis();
		int[] idom = dominators(nNodes, g.off, g.adj);
		Result r = new Result();
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
		// self-check: the immediate dominator of a sample of application sites must dominate
		int want = Integer.getInteger("ownership.check", 40), checked = 0, bad = 0;
		for (int i = 0; i < ns && checked < want; i++) {
			if (!isApp(sites.get(i)) || idom[siteBase + i] < 0) continue;
			checked++;
			if (!dominates(nNodes, g.off, g.adj, idom[siteBase + i], siteBase + i)) {
				bad++;
				System.out.println("[ownership] CHECK FAILED: " + nodeName(idom[siteBase + i]) + " does not dominate "
						+ nodeName(siteBase + i));
			}
		}
		System.out.println("[ownership] check " + label + ": " + checked + " application sites, " + bad + " failures");
		// explain: for sites whose name contains the property's text, a path that avoids the
		// allocating method, which is what keeps the site from being OWN
		String ex = System.getProperty("ownership.explain");
		if (ex != null) {
			for (int i = 0; i < ns; i++) {
				AllocNode an = sites.get(i);
				if (an.getMethod() == null || !siteName(an).contains(ex)) continue;
				int[] p = witness(nNodes, g.off, g.adj, mNode(an.getMethod()), siteBase + i);
				StringBuilder sb = new StringBuilder("[ownership] explain " + label + " " + siteName(an) + ":");
				if (p == null) sb.append(" every path passes the allocating method");
				else for (int v : p) sb.append("\n      ").append(nodeName(v));
				System.out.println(sb);
			}
		}
		return r;
	}

	// ------------------------------------------------------------------ why a site is HEAP

	/** BFS parents from src (-1 at src, -2 unreached); `skip` is treated as absent. */
	static int[] bfsParents(int n, int[] off, int[] adj, int src, int skip) {
		int[] parent = new int[n];
		Arrays.fill(parent, -2);
		int[] q = new int[n];
		int h = 0, t = 0;
		q[t++] = src; parent[src] = -1;
		if (skip >= 0) parent[skip] = -3;
		while (h < t) {
			int v = q[h++];
			for (int i = off[v]; i < off[v + 1]; i++)
				if (parent[adj[i]] == -2) { parent[adj[i]] = v; q[t++] = adj[i]; }
		}
		if (skip >= 0) parent[skip] = -2;
		return parent;
	}

	static List<Integer> trace(int[] parent, int v) {
		List<Integer> p = new ArrayList<>();
		for (int x = v; x >= 0; x = parent[x]) p.add(x);
		Collections.reverse(p);
		return p;
	}

	String shortName(int v) {
		if (v < siteBase) return v == 0 ? "ROOT" : v == 1 ? "GLOBAL" : methods.get(v - 2).getSignature();
		if (v >= unsafeBase) return "Unsafe store in " + unsafeMethods.get(v - unsafeBase).getSignature();
		AllocNode an = sites.get(v - siteBase);
		String n = siteName(an);
		int bar = n.indexOf('|');
		return bar < 0 ? n : an.getType() + "@" + an.getMethod().getDeclaringClass().getName() + "."
				+ an.getMethod().getName() + ":" + n.substring(bar + 1, n.lastIndexOf('|'));
	}

	/** The edge that reaches v on the path: GLOBAL directly, a frame, or <site type>.<field>. */
	String via(List<Integer> path) {
		if (path.size() < 2) return "-";
		int p = path.get(path.size() - 2), v = path.get(path.size() - 1);
		if (p == 1) return "GLOBAL";
		if (p < siteBase) return "frame";
		if (p >= unsafeBase) return "Unsafe store in " + unsafeMethods.get(p - unsafeBase).getDeclaringClass().getName();
		AllocNode pa = sites.get(p - siteBase), va = sites.get(v - siteBase);
		List<String> fs = new ArrayList<>();
		for (AllocDotField f : pa.getFields())
			if (f.getP2Set().contains(va)) fs.add(f.getField().toString());
		Collections.sort(fs);
		return pa.getType() + "." + (fs.isEmpty() ? "?" : String.join("|", fs));
	}

	void attribute(Graph g, Result r, Integer[] ord, String[] names) throws IOException {
		attribute(g, r, ord, names, "", "B");
	}

	void attribute(Graph g, Result r, Integer[] ord, String[] names, String suffix, String label) throws IOException {
		int[] pg = bfsParents(nNodes, g.off, g.adj, 1, -1);
		int[] pr = bfsParents(nNodes, g.off, g.adj, 0, 1);
		Map<String, Integer> byKind = new TreeMap<>(), byDetail = new HashMap<>(), byVia = new HashMap<>();
		try (BufferedWriter w = Files.newBufferedWriter(Paths.get(outDir, name + ".ownwhy" + suffix), StandardCharsets.UTF_8)) {
			w.write("# site\troot\tdetail\tvia\tlength\tpath\n");
			for (int i : ord) {
				if (!isApp(sites.get(i)) || !"HEAP".equals(r.cls[i])) continue;
				int v = siteBase + i;
				List<Integer> path;
				String kind, detail;
				if (pg[v] != -2) {
					path = trace(pg, v);
					String why = path.size() > 1 ? globalWhy.getOrDefault(path.get(1), "unlabelled:?") : "unlabelled:?";
					int c = why.indexOf(':');
					kind = why.substring(0, c);
					detail = why.substring(c + 1);
				} else if (pr[v] != -2) {
					// reachable only from ROOT's entries, and no method dominates: two stacks,
					// or two entry points, reach it
					path = trace(pr, v);
					kind = "entries";
					detail = path.size() > 1 ? shortName(path.get(1)) : "?";
				} else {
					path = Collections.singletonList(v);
					kind = "unreached";
					detail = "-";
				}
				String vi = via(path);
				StringBuilder ps = new StringBuilder();
				for (int k = 0; k < path.size(); k++) {
					if (path.size() > 8 && k == 3) { ps.append(" > ..."); k = path.size() - 4; continue; }
					if (k > 0) ps.append(" > ");
					ps.append(shortName(path.get(k)));
				}
				w.write(names[i] + "\t" + kind + "\t" + detail + "\t" + vi + "\t" + path.size() + "\t" + ps + "\n");
				byKind.merge(kind, 1, Integer::sum);
				byDetail.merge(kind + ":" + detail, 1, Integer::sum);
				byVia.merge(vi, 1, Integer::sum);
			}
		}
		System.out.println("[ownership] why HEAP (" + label + "): " + byKind);
		System.out.println("[ownership]   top causes: " + top(byDetail, 8));
		System.out.println("[ownership]   top last edges: " + top(byVia, 8));
	}

	static String top(Map<String, Integer> m, int k) {
		List<Map.Entry<String, Integer>> l = new ArrayList<>(m.entrySet());
		l.sort((a, b) -> b.getValue() - a.getValue());
		StringBuilder sb = new StringBuilder();
		for (int i = 0; i < Math.min(k, l.size()); i++)
			sb.append(i == 0 ? "" : "; ").append(l.get(i).getValue()).append(" ").append(l.get(i).getKey());
		return sb.toString();
	}

	static boolean isApp(AllocNode an) {
		return an.getMethod() != null && an.getMethod().getDeclaringClass().isApplicationClass() && !isToken(an);
	}

	void run() throws IOException {
		number();
		findUnsafeStores();
		System.out.println("[ownership] " + unsafeUnits.size() + " Unsafe object stores modelled as heap edges");
		computeReturns();
		methodSccs();
		Graph gb = new Graph();
		common(gb);
		System.out.println("[ownership] " + entries.size() + " entry points, " + asyncEntries.size()
				+ " async targets" + (asyncEntries.size() <= 40 ? ": " + asyncTargets.keySet() : ""));
		borrowFrames(gb);
		System.out.println("[ownership] frame edges B: " + newEdges + " allocations, " + callEdgesKept
				+ " calls kept, " + callEdgesDropped + " calls dropped as parameter-derived, " + caughtEdges
				+ " catch handlers (" + caughtKept + " thrown sites kept, " + caughtDropped
				+ " dropped as never thrown below the handler), " + fallbacks
				+ " fell back to the local's points-to set; " + unknownCalls
				+ " calls to bodiless methods that may keep their arguments");
		String[] names = new String[sites.size()];
		for (int i = 0; i < sites.size(); i++) names[i] = siteName(sites.get(i));
		Integer[] ord = new Integer[sites.size()];
		for (int i = 0; i < ord.length; i++) ord[i] = i;
		Arrays.sort(ord, Comparator.comparing(i -> names[i]));

		Result b = classify(gb, "B");
		attribute(gb, b, ord, names);
		gb = null;                       // only one graph in memory at a time
		Graph gn = new Graph();
		common(gn);
		naiveFrames(gn);
		Result nv = classify(gn, "N");

		try (BufferedWriter w = Files.newBufferedWriter(Paths.get(outDir, name + ".own"), StandardCharsets.UTF_8)) {
			w.write("# site\tapp\tB.class\tB.region\tB.owner\tB.up\tB.recursive\tN.class\tN.region\tN.up\n");
			for (int i : ord) {
				if (sites.get(i).getMethod() == null || isToken(sites.get(i))) continue;
				w.write(names[i] + "\t" + (isApp(sites.get(i)) ? 1 : 0) + "\t" + b.cls[i] + "\t" + b.region[i] + "\t"
						+ b.owner[i] + "\t" + b.up[i] + "\t" + (b.rec[i] ? 1 : 0) + "\t" + nv.cls[i] + "\t"
						+ nv.region[i] + "\t" + nv.up[i] + "\n");
			}
		}
		try (BufferedWriter w = Files.newBufferedWriter(Paths.get(outDir, name + ".owntree"), StandardCharsets.UTF_8)) {
			for (int i : ord) {
				if (!isApp(sites.get(i))) continue;
				int v = siteBase + i;
				StringBuilder sb = new StringBuilder(names[i]);
				if (b.idom[v] == -1) sb.append("\n    (unreachable)");
				else for (int x = b.idom[v]; ; x = b.idom[x]) {
					sb.append("\n    <- ").append(nodeName(x));
					if (x == 0) break;
				}
				w.write(sb.append("\n").toString());
			}
		}
		summary("B", b);
		summary("N", nv);
		if (Boolean.getBoolean("ownership.whatif")) whatIf(b, ord, names);
	}

	/** Graph B again with the what-if switches: S (special sinks), P (phantom no-op), SP (both). */
	void whatIf(Result b, Integer[] ord, String[] names) throws IOException {
		String[] labels = {"S", "P", "SP"};
		Result[] rs = new Result[3];
		for (int k = 0; k < 3; k++) {
			specialSinks = k != 1;
			phantomNoop = k != 0;
			Graph g = new Graph();
			common(g);
			borrowFrames(g);
			rs[k] = classify(g, labels[k]);
			if (k == 2) attribute(g, rs[k], ord, names, "-sp", "SP");
			summary(labels[k], rs[k]);
		}
		specialSinks = phantomNoop = false;
		try (BufferedWriter w = Files.newBufferedWriter(Paths.get(outDir, name + ".ownwhatif"), StandardCharsets.UTF_8)) {
			w.write("# what-if, not sound: S = Spark's special nodes keep no fields, P = phantom callees keep nothing\n");
			w.write("# site\tapp\tB.class\tB.up\tS.class\tS.up\tP.class\tP.up\tSP.class\tSP.up\n");
			for (int i : ord) {
				if (sites.get(i).getMethod() == null || isToken(sites.get(i))) continue;
				StringBuilder sb = new StringBuilder(names[i]).append('\t').append(isApp(sites.get(i)) ? 1 : 0)
						.append('\t').append(b.cls[i]).append('\t').append(b.up[i]);
				for (Result r : rs) sb.append('\t').append(r.cls[i]).append('\t').append(r.up[i]);
				w.write(sb.append('\n').toString());
			}
		}
	}

	void summary(String label, Result r) {
		Map<String, Integer> c = new TreeMap<>();
		int app = 0, recOwn = 0;
		for (int i = 0; i < sites.size(); i++) {
			if (!isApp(sites.get(i))) continue;
			app++;
			String k = r.cls[i].equals("UP") ? "UP" + (r.up[i] >= 3 ? "3+" : String.valueOf(r.up[i])) : r.cls[i];
			c.merge(k, 1, Integer::sum);
			if (r.cls[i].equals("OWN") && r.rec[i]) recOwn++;
		}
		System.out.println("[ownership] " + label + ": " + app + " application sites " + c + ", OWN in a recursive method "
				+ recOwn);
	}
}
