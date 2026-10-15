package heapviz;

import java.util.*;
import soot.*;
import soot.jimple.*;
import soot.jimple.spark.pag.AllocNode;
import soot.jimple.spark.pag.Node;
import soot.jimple.spark.sets.P2SetVisitor;
import soot.jimple.spark.sets.PointsToSetInternal;
import soot.jimple.toolkits.callgraph.Edge;

/**
 * Computes Scope LCA (Call-Graph Dominance) for static fields to bind
 * static object lifetimes to their capturing method frames.
 */
class StaticFieldLiveness {

	final OwnershipTree tree;
	final Map<SootField, Set<SootMethod>> fieldAccessors = new HashMap<>();
	final Map<SootField, SootMethod> fieldCapturingMethod = new HashMap<>();
	int[] sccIdom;
	final Set<Integer> entrySccs = new HashSet<>();
	int scopedFieldsCount = 0;
	int persistentFieldsCount = 0;

	StaticFieldLiveness(OwnershipTree tree) {
		this.tree = tree;
	}

	/**
	 * Computes immediate dominators on the Call Graph SCC DAG.
	 */
	void computeSccDominators() {
		int nScc = tree.sccSucc.size();
		// Node 0: Super-root pointing to all entry SCCs.
		// Node k + 1: SCC k.
		List<List<Integer>> adj = new ArrayList<>();
		for (int i = 0; i <= nScc; i++) adj.add(new ArrayList<>());

		entrySccs.clear();
		for (SootMethod ep : tree.entries) {
			Integer mid = tree.methodId.get(ep);
			if (mid != null) {
				int scc = tree.sccOf[mid];
				entrySccs.add(scc);
				adj.get(0).add(scc + 1);
			}
		}
		for (SootMethod m : tree.methods) {
			for (Iterator<Edge> it = tree.cg.edgesOutOf(m); it.hasNext(); ) {
				Edge e = it.next();
				if (GraphBuilder.async(e.kind()) && !GraphBuilder.emptyFinalizer(e)) {
					Integer mid = tree.methodId.get(e.tgt());
					if (mid != null) {
						int scc = tree.sccOf[mid];
						entrySccs.add(scc);
						adj.get(0).add(scc + 1);
					}
				}
			}
		}

		for (int i = 0; i < nScc; i++) {
			for (int j : tree.sccSucc.get(i)) {
				adj.get(i + 1).add(j + 1);
			}
		}

		int[] off = new int[nScc + 2];
		for (int i = 0; i <= nScc; i++) off[i + 1] = off[i] + adj.get(i).size();
		int[] flatAdj = new int[off[nScc + 1]];
		int p = 0;
		for (int i = 0; i <= nScc; i++) {
			for (int tgt : adj.get(i)) flatAdj[p++] = tgt;
		}

		sccIdom = Dominators.dominators(nScc + 1, off, flatAdj);
	}

	/**
	 * Finds Lowest Common Ancestor (LCA) in the dominator tree.
	 */
	int lca(int u, int v) {
		if (u == v) return u;
		Set<Integer> anc = new HashSet<>();
		for (int x = u; x >= 0; x = sccIdom[x]) {
			anc.add(x);
			if (x == 0) break;
		}
		for (int y = v; y >= 0; y = sccIdom[y]) {
			if (anc.contains(y)) return y;
			if (y == 0) break;
		}
		return 0;
	}

	/**
	 * Scans all reachable methods for static field references and <clinit> triggers.
	 */
	void collectAccessors() {
		fieldAccessors.clear();
		for (SootMethod m : tree.methods) {
			if (!m.hasActiveBody()) continue;
			for (Unit u : m.getActiveBody().getUnits()) {
				Stmt s = (Stmt) u;
				if (s.containsFieldRef() && s.getFieldRef() instanceof StaticFieldRef) {
					SootField f = s.getFieldRef().getField();
					fieldAccessors.computeIfAbsent(f, k -> new HashSet<>()).add(m);
				}
				// <clinit> trigger attribution
				for (Iterator<Edge> it = tree.cg.edgesOutOf(u); it.hasNext(); ) {
					Edge e = it.next();
					if (e.kind() == Kind.CLINIT) {
						SootMethod clinit = e.tgt();
						for (SootField f : clinit.getDeclaringClass().getFields()) {
							if (f.isStatic()) {
								fieldAccessors.computeIfAbsent(f, k -> new HashSet<>()).add(m);
							}
						}
					}
				}
			}
		}
	}

	/**
	 * Resolves the capturing method for each static field via Scope LCA.
	 */
	void findStaticLifetimes() {
		computeSccDominators();
		collectAccessors();
		fieldCapturingMethod.clear();
		scopedFieldsCount = 0;
		persistentFieldsCount = 0;

		for (Map.Entry<SootField, Set<SootMethod>> en : fieldAccessors.entrySet()) {
			SootField f = en.getKey();
			Set<SootMethod> acc = en.getValue();
			if (acc.isEmpty()) continue;

			Iterator<SootMethod> it = acc.iterator();
			int curr = tree.sccOf[tree.methodId.get(it.next())] + 1;
			while (it.hasNext() && curr != 0) {
				int next = tree.sccOf[tree.methodId.get(it.next())] + 1;
				curr = lca(curr, next);
			}

			if (curr == 0 || entrySccs.contains(curr - 1)) {
				// Globally persistent static field
				fieldCapturingMethod.put(f, null);
				persistentFieldsCount++;
			} else {
				// Method-scoped static field
				int capScc = curr - 1;
				SootMethod capMethod = null;
				// Find entry method for the capturing SCC
				for (SootMethod m : tree.methods) {
					if (tree.sccOf[tree.methodId.get(m)] == capScc) {
						if (capMethod == null) capMethod = m;
						// Prefer entry method into SCC if reachable from outside
						for (Iterator<Edge> eit = tree.cg.edgesInto(m); eit.hasNext(); ) {
							SootMethod src = eit.next().src();
							Integer smid = tree.methodId.get(src);
							if (smid != null && tree.sccOf[smid] != capScc) {
								capMethod = m;
								break;
							}
						}
					}
				}
				fieldCapturingMethod.put(f, capMethod);
				scopedFieldsCount++;
			}
		}

		System.out.println("[ownership] static field liveness (Scope LCA): " + scopedFieldsCount
				+ " method-scoped static fields, " + persistentFieldsCount + " globally persistent");
	}

	/**
	 * Returns the capturing method for a static field, or null if globally persistent.
	 */
	SootMethod getCapturingMethod(SootField f) {
		return fieldCapturingMethod.get(f);
	}

	/**
	 * Connects a method-scoped static field to its points-to set under capturing method M.
	 */
	void connectStatic(OwnershipGraph g, SootField f, SootMethod cap, PointsToSet pts) {
		if (!(pts instanceof PointsToSetInternal)) return;
		int mn = tree.mNode(cap);
		((PointsToSetInternal) pts).forall(new P2SetVisitor() {
			@Override public void visit(Node n) {
				if (!(n instanceof AllocNode) || !tree.siteId.containsKey(n)) return;
				int s = tree.sNode((AllocNode) n);
				g.edge(mn, s);
			}
		});
	}
}
