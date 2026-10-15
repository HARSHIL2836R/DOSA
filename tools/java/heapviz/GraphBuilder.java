package heapviz;

import java.util.*;
import soot.*;
import soot.jimple.*;
import soot.jimple.spark.pag.*;
import soot.jimple.spark.sets.P2SetVisitor;
import soot.jimple.spark.sets.PointsToSetInternal;
import soot.jimple.toolkits.callgraph.Edge;
import soot.Kind;

/**
 * Builds ownership graphs according to borrow and naive framing rules.
 */
class GraphBuilder {

	final OwnershipTree tree;

	// Why each node hangs directly off GLOBAL (first reason recorded)
	final Map<Integer, String> globalWhy = new HashMap<>();

	// What-if switches (ownership.whatif=true)
	boolean specialSinks, phantomNoop;

	int newEdges, callEdgesKept, callEdgesDropped, caughtEdges, fallbacks;
	int caughtKept, caughtDropped;
	int unknownCalls;
	boolean throwersCollected;

	final Set<SootMethod> asyncEntries = new HashSet<>();
	final Map<String, Integer> asyncTargets = new TreeMap<>();

	final Map<Integer, List<Integer>> throwers = new HashMap<>();
	final Map<Integer, BitSet> reachFrom = new HashMap<>();

	// TODO: What are these Retaining Natives
	static final Set<String> RETAINING_JDK_NATIVES = new HashSet<>(Arrays.asList(
			"<java.lang.String: java.lang.String intern()>",
			"<java.lang.Thread: void start0()>"));

	/**
	 * Creates a new GraphBuilder bound to the given OwnershipTree.
	 *
	 * @param tree the enclosing OwnershipTree instance
	 */
	GraphBuilder(OwnershipTree tree) {
		this.tree = tree;
	}

	/**
	 * Checks if an allocation node represents a special Spark node.
	 *
	 * @param an the allocation node
	 * @return true if the node is special
	 */
	static boolean isSpecial(AllocNode an) {
		return an.getMethod() == null && !SiteNaming.isToken(an);
	}

	/**
	 * Checks if an edge kind represents an asynchronous execution target.
	 *
	 * @param k the call graph edge kind
	 * @return true if asynchronous
	 */
	static boolean async(Kind k) {
		return k.isThread() || k.isExecutor() || k.isAsyncTask() || k == Kind.FINALIZE
				|| k == Kind.INVOKE_FINALIZE || k == Kind.HANDLER;
	}

	/**
	 * Identifies empty finalizers such as Object.finalize() that hold no references.
	 *
	 * @param e the call edge
	 * @return true if the edge targets an empty finalizer
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

	/**
	 * Checks if a bodiless method may keep a reference to passed parameters.
	 *
	 * @param t the target method
	 * @return true if the method may retain parameters
	 */
	static boolean retains(SootMethod t) {
		String c = t.getDeclaringClass().getName();
		boolean jdk = c.startsWith("java.") || c.startsWith("javax.") || c.startsWith("sun.")
				|| c.startsWith("com.sun.") || c.startsWith("jdk.");
		return !jdk || RETAINING_JDK_NATIVES.contains(t.getSignature());
	}

	/**
	 * Connects global node (1) to all allocation sites in the given points-to set.
	 *
	 * @param g the graph
	 * @param why reason string for global attribution
	 * @param pts points-to set of targets
	 */
	void global(OwnershipGraph g, String why, PointsToSet pts) {
		if (!(pts instanceof PointsToSetInternal)) return;
		((PointsToSetInternal) pts).forall(new P2SetVisitor() {
			@Override public void visit(Node n) {
				if (!(n instanceof AllocNode) || !tree.siteId.containsKey(n)) return;
				int s = tree.sNode((AllocNode) n);
				g.edge(1, s);
				globalWhy.putIfAbsent(s, why);
			}
		});
	}

	/**
	 * Populates edges shared by all graph variants: root, calls, statics, special nodes, heap fields.
	 *
	 * @param g the graph to populate
	 */
	void common(OwnershipGraph g) {
		globalWhy.clear();
		g.edge(0, 1);
		for (SootMethod ep : tree.entries) g.edge(0, tree.mNode(ep));
		for (SootMethod m : tree.methods) {
			for (Iterator<Edge> it = tree.cg.edgesOutOf(m); it.hasNext(); ) {
				Edge e = it.next();
				if (!tree.methodId.containsKey(e.tgt())) continue;
				if (emptyFinalizer(e)) continue;
				if (async(e.kind())) {
					g.edge(0, tree.mNode(e.tgt()));
					if (asyncEntries.add(e.tgt())) asyncTargets.merge(e.kind() + " " + e.tgt(), 1, Integer::sum);
				} else g.edge(tree.mNode(m), tree.mNode(e.tgt()));
			}
		}
		for (AllocNode an : tree.sites) {
			if (an.getMethod() == null || SiteNaming.isToken(an)) {
				g.edge(1, tree.sNode(an));
				globalWhy.putIfAbsent(tree.sNode(an), "special:" + tree.naming.siteName(an));
			}
			if (specialSinks && isSpecial(an)) continue;
			for (AllocDotField f : an.getFields()) g.toSites(tree.sNode(an), f.getP2Set());
		}
		tree.unsafeStores.unsafeEdges(g);
		boolean useScopeLca = Boolean.parseBoolean(System.getProperty("ownership.scopeLca", "true"));
		for (VarNode v : tree.pag.getVarNodeNumberer()) {
			if (v instanceof GlobalVarNode && v.getVariable() instanceof SootField) {
				SootField sf = (SootField) v.getVariable();
				SootMethod cap = useScopeLca ? tree.staticLiveness.getCapturingMethod(sf) : null;
				if (cap != null) {
					tree.staticLiveness.connectStatic(g, sf, cap, v.getP2Set());
				} else {
					global(g, "static:" + sf.getSignature(), v.getP2Set());
				}
			}
		}
		for (SootMethod m : tree.methods) {
			if (!m.hasActiveBody()) continue;
			for (Unit u : m.getActiveBody().getUnits()) {
				if (!(u instanceof Stmt) || !((Stmt) u).containsInvokeExpr()) continue;
				InvokeExpr ie = ((Stmt) u).getInvokeExpr();
				for (Iterator<Edge> it = tree.cg.edgesOutOf(u); it.hasNext(); ) {
					SootMethod t = it.next().tgt();
					if (t.hasActiveBody() || !retains(t)) continue;
					if (phantomNoop && t.getDeclaringClass().isPhantom()) continue;
					unknownCalls++;
					String why = (t.getDeclaringClass().isPhantom() ? "phantom-arg:" : "native-arg:") + t.getSignature();
					if (ie instanceof InstanceInvokeExpr) global(g, why, tree.pag.reachingObjects((Local) ((InstanceInvokeExpr) ie).getBase()));
					for (Value v : ie.getArgs())
						if (v instanceof Local && v.getType() instanceof RefLikeType) global(g, why, tree.pag.reachingObjects((Local) v));
				}
			}
		}
		for (SootMethod m : tree.methods) {
			if (!m.hasActiveBody() || !(tree.entries.contains(m) || asyncEntries.contains(m))) continue;
			for (Unit u : m.getActiveBody().getUnits()) {
				if (!(u instanceof IdentityStmt)) continue;
				IdentityStmt is = (IdentityStmt) u;
				if ((is.getRightOp() instanceof ThisRef || is.getRightOp() instanceof ParameterRef)
						&& is.getLeftOp() instanceof Local)
					global(g, (tree.entries.contains(m) ? "entry-param:" : "thread-param:") + m.getSignature(),
							tree.pag.reachingObjects((Local) is.getLeftOp()));
			}
		}
	}

	/**
	 * Collects methods throwing each allocation site.
	 */
	void collectThrowers() {
		for (SootMethod m : tree.methods) {
			if (!m.hasActiveBody()) continue;
			int mi = tree.methodId.get(m);
			for (Unit u : m.getActiveBody().getUnits()) {
				if (!(u instanceof ThrowStmt) || !(((ThrowStmt) u).getOp() instanceof Local)) continue;
				PointsToSet pts = tree.pag.reachingObjects((Local) ((ThrowStmt) u).getOp());
				if (!(pts instanceof PointsToSetInternal)) continue;
				((PointsToSetInternal) pts).forall(new P2SetVisitor() {
					@Override public void visit(Node n) {
						Integer s = tree.siteId.get(n);
						if (s != null) throwers.computeIfAbsent(s, k -> new ArrayList<>()).add(mi);
					}
				});
			}
		}
	}

	/**
	 * Returns call-graph reachability bitset from method index mi.
	 *
	 * @param mi source method index
	 * @return reachable method bitset
	 */
	BitSet reach(int mi) {
		return reachFrom.computeIfAbsent(mi, k -> {
			BitSet seen = new BitSet();
			Deque<Integer> q = new ArrayDeque<>();
			q.add(k); seen.set(k);
			while (!q.isEmpty()) {
				SootMethod m = tree.methods.get(q.poll());
				for (Iterator<Edge> it = tree.cg.edgesOutOf(m); it.hasNext(); ) {
					Edge e = it.next();
					Integer t = tree.methodId.get(e.tgt());
					if (t != null && !async(e.kind()) && !seen.get(t)) { seen.set(t); q.add(t); }
				}
			}
			return seen;
		});
	}

	/**
	 * Adds edges from catch handler frame to caught exception allocation sites reachable in call graph.
	 *
	 * @param g the graph
	 * @param h the handler method
	 * @param l the caught exception local variable
	 */
	void caughtEdges(OwnershipGraph g, SootMethod h, Local l) {
		PointsToSet pts = tree.pag.reachingObjects(l);
		if (!(pts instanceof PointsToSetInternal)) return;
		BitSet r = reach(tree.methodId.get(h));
		int hn = tree.mNode(h);
		((PointsToSetInternal) pts).forall(new P2SetVisitor() {
			@Override public void visit(Node n) {
				Integer s = tree.siteId.get(n);
				if (s == null) return;
				boolean ok = false;
				for (int t : throwers.getOrDefault(s, Collections.emptyList())) if (r.get(t)) { ok = true; break; }
				if (ok) { g.edge(hn, tree.siteBase + s); caughtKept++; } else caughtDropped++;
			}
		});
	}

	/**
	 * Populates frame edges under the borrow rule (OwnershipGraph B).
	 *
	 * @param g the graph to populate
	 */
	void borrowFrames(OwnershipGraph g) {
		if (!throwersCollected) { collectThrowers(); throwersCollected = true; }
		for (SootMethod m : tree.methods) {
			if (!m.hasActiveBody()) continue;
			int mn = tree.mNode(m);
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
					AllocNode an = tree.byNewExpr.get(r);
					if (an != null && tree.siteId.containsKey(an)) g.edge(mn, tree.sNode(an));
					else { g.toSites(mn, tree.pag.reachingObjects(lhs)); fallbacks++; }
					newEdges++;
				} else if (r instanceof InvokeExpr) {
					if (d == null) d = tree.returnAnalysis.derive(m);
					if ((tree.returnAnalysis.callValue(u, (InvokeExpr) r, d) & OwnershipTree.TOP) == 0) { callEdgesDropped++; continue; }
					callEdgesKept++;
					boolean fellBack = false;
					Iterator<Edge> it = tree.cg.edgesOutOf(u);
					if (!it.hasNext()) fellBack = true;
					while (it.hasNext()) {
						Edge e = it.next();
						if (e.kind() == Kind.CLINIT) continue;
						Long rp = tree.retParams.get(e.tgt());
						if (!e.kind().isExplicit() || rp == null || !e.tgt().hasActiveBody()) { fellBack = true; continue; }
						if ((rp & OwnershipTree.TOP) == 0) continue;
						LocalVarNode rn = tree.pag.findLocalVarNode(Parm.v(e.tgt(), PointsToAnalysis.RETURN_NODE));
						if (rn == null) fellBack = true;
						else g.toSites(mn, rn.getP2Set());
					}
					if (fellBack) { g.toSites(mn, tree.pag.reachingObjects(lhs)); fallbacks++; }
				}
			}
		}
	}

	/**
	 * Populates frame edges where every local points to its whole points-to set (OwnershipGraph N).
	 *
	 * @param g the graph to populate
	 */
	void naiveFrames(OwnershipGraph g) {
		for (SootMethod m : tree.methods) {
			if (!m.hasActiveBody()) continue;
			int mn = tree.mNode(m);
			for (Local l : m.getActiveBody().getLocals())
				if (l.getType() instanceof RefLikeType) g.toSites(mn, tree.pag.reachingObjects(l));
		}
	}
}
