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
 * Handles detection and modeling of {@code sun.misc.Unsafe} object store calls.
 * Models them as heap edges rather than global edges.
 */
class UnsafeStoreHandler {

	final OwnershipTree tree;

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

	// One node per Unsafe store call site: every object the call may write into points to it,
	// and it points to every value written. Linking the two sets directly would multiply them.
	final List<Unit> unsafeUnits = new ArrayList<>();
	final List<SootMethod> unsafeMethods = new ArrayList<>();
	int unsafeBase;

	/**
	 * Creates a new UnsafeStoreHandler bound to the given OwnershipTree.
	 *
	 * @param tree the enclosing OwnershipTree instance
	 */
	UnsafeStoreHandler(OwnershipTree tree) {
		this.tree = tree;
	}

	/**
	 * Scans reachable methods for calls to {@code sun.misc.Unsafe} store methods.
	 * Allocates node IDs for them in the ownership graph numbering.
	 */
	void findUnsafeStores() {
		for (SootMethod m : tree.methods) {
			if (!m.hasActiveBody()) continue;
			for (Unit u : m.getActiveBody().getUnits()) {
				if (!(u instanceof Stmt) || !((Stmt) u).containsInvokeExpr()) continue;
				for (Iterator<Edge> it = tree.cg.edgesOutOf(u); it.hasNext(); )
					if (UNSAFE_STORES.containsKey(it.next().tgt().getSignature())) {
						unsafeUnits.add(u);
						unsafeMethods.add(m);
						break;
					}
			}
		}
		unsafeBase = tree.siteBase + tree.sites.size();
		tree.nNodes = unsafeBase + unsafeUnits.size();
	}

	/**
	 * Adds edges for Unsafe object stores to the ownership graph.
	 *
	 * @param g the ownership graph to populate
	 */
	void unsafeEdges(OwnershipGraph g) {
		for (int k = 0; k < unsafeUnits.size(); k++) {
			InvokeExpr ie = ((Stmt) unsafeUnits.get(k)).getInvokeExpr();
			int node = unsafeBase + k;
			Integer vi = null;
			for (Iterator<Edge> it = tree.cg.edgesOutOf(unsafeUnits.get(k)); it.hasNext(); ) {
				Integer x = UNSAFE_STORES.get(it.next().tgt().getSignature());
				if (x != null) vi = x;
			}
			if (vi == null || ie.getArgCount() <= vi) continue;
			Value o = ie.getArg(0), v = ie.getArg(vi);
			if (!(o instanceof Local) || !(v instanceof Local)) continue;
			PointsToSet po = tree.pag.reachingObjects((Local) o);
			if (po instanceof PointsToSetInternal)
				((PointsToSetInternal) po).forall(new P2SetVisitor() {
					@Override public void visit(Node n) {
						if (n instanceof AllocNode && tree.siteId.containsKey(n)) g.edge(tree.sNode((AllocNode) n), node);
					}
				});
			g.toSites(node, tree.pag.reachingObjects((Local) v));
		}
	}
}
