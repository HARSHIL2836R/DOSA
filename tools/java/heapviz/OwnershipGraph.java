package heapviz;

import soot.jimple.spark.pag.AllocNode;
import soot.jimple.spark.sets.P2SetVisitor;
import soot.jimple.spark.sets.PointsToSetInternal;
import soot.jimple.spark.pag.Node;
import soot.PointsToSet;

import java.util.Arrays;
import java.util.BitSet;

public final class OwnershipGraph {

    OwnershipTree tree;

    public OwnershipGraph(OwnershipTree tree) {
        this.tree = tree;
    }
	
		IntList edgeSources = new IntList(), edgeTargets = new IntList();
		int edges;
		// Edges from one source usually arrive together (one method's locals, one site's
		// fields), so they are collected in a set and written once: graph N on the corpus had
		// 34 million edges before this, most of them repeats.
		final BitSet pending = new BitSet();
		int pendingSrc = -1;
		void flush() {
			for (int target = pending.nextSetBit(0); target >= 0; target = pending.nextSetBit(target + 1)) { edgeSources.add(pendingSrc); edgeTargets.add(target); }
			pending.clear();
		}
		/**
		 * Adds a directed edge from source to target.
		 * @param source the source node index
		 * @param target the target node index
		 */
		void edge(int source, int target) {
			if (source != pendingSrc) { flush(); pendingSrc = source; }
			pending.set(target);
		}
		/**
		 * Adds edges from source to all allocation nodes in the given points-to set.
		 * @param source the source node index
		 * @param pts the points-to set containing targets
		 */
		void toSites(int source, PointsToSet pts) {
			if (!(pts instanceof PointsToSetInternal)) return;
			((PointsToSetInternal) pts).forall(new P2SetVisitor() {
				@Override public void visit(Node n) {
					if (n instanceof AllocNode && tree.siteId.containsKey(n)) edge(source, tree.sNode((AllocNode) n));
				}
			});
		}
		/** Offset array for CSR format graph. */
		int[] offsets;
		/** Adjacency array for CSR format graph. */
		int[] adjacency;
		/**
		 * Freezes the edge list into a CSR (Compressed Sparse Row) representation for fast traversal.
		 */
		void freeze() {
			flush();
			offsets = new int[tree.nNodes + 1];
			for (int i = 0; i < edgeSources.count; i++) offsets[edgeSources.data[i] + 1]++;
			for (int i = 0; i < tree.nNodes; i++) offsets[i + 1] += offsets[i];
			adjacency = new int[edgeSources.count];
			int[] pos = Arrays.copyOf(offsets, tree.nNodes);
			for (int i = 0; i < edgeSources.count; i++) adjacency[pos[edgeSources.data[i]]++] = edgeTargets.data[i];
			edges = edgeSources.count;
			edgeSources = null; edgeTargets = null;
		}
	
}
