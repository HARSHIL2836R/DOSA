package heapviz;

public final class OwnershipResult {
	
		/** Immediate dominator for each node. */
		int[] idom;
		/** Classification of each site (OWN, UP, HEAP, UNREACHED). */
		String[] cls;
		/** The method region name for each site. */
		String[] region;
		/** The owner type name (ROOT, GLOBAL, FRAME, OBJECT). */
		String[] owner;
		/** The distance up the call graph (dominator distance). */
		int[] up;
		/** True if the method region is in a recursive SCC. */
		boolean[] rec;
	
}
