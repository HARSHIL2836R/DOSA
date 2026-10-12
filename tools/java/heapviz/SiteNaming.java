package heapviz;

import java.util.*;
import soot.*;
import soot.jimple.*;
import soot.jimple.spark.pag.AllocNode;
import soot.PointsToAnalysis;
import soot.tagkit.BytecodeOffsetTag;
import soot.toolkits.scalar.Pair;

/**
 * Naming and display utilities for allocation sites and graph nodes.
 */
class SiteNaming {

	final OwnershipTree tree;

	final Map<SootMethod, IdentityHashMap<Object, Unit>> allocUnits = new HashMap<>();

	/**
	 * Creates a new SiteNaming bound to the given OwnershipTree.
	 *
	 * @param tree the enclosing OwnershipTree instance
	 */
	SiteNaming(OwnershipTree tree) {
		this.tree = tree;
	}

	/**
	 * Checks whether the allocation node represents a token (string, class constant, or type).
	 *
	 * @param an the allocation node
	 * @return true if the node is a token node
	 */
	static boolean isToken(AllocNode an) {
		Object e = an.getNewExpr();
		if (e instanceof Pair) e = ((Pair<?, ?>) e).getO1();
		return e == PointsToAnalysis.STRING_NODE || e instanceof ClassConstant || e instanceof Type;
	}

	/**
	 * Extracts the bytecode offset tag from an allocation unit.
	 *
	 * @param u the Jimple unit
	 * @return the bytecode offset, or null if not available
	 */
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

	/**
	 * Returns the formatted string name for an allocation site.
	 *
	 * @param an the allocation node
	 * @return the descriptive site name
	 */
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

	/**
	 * Returns a descriptive name for a graph node index.
	 *
	 * @param v the node index
	 * @return the string name of the node
	 */
	String nodeName(int v) {
		if (v == 0) return "ROOT";
		if (v == 1) return "GLOBAL";
		if (v < tree.siteBase) return "M:" + tree.methods.get(v - 2);
		int unsafeBase = tree.unsafeStores.unsafeBase;
		if (v >= unsafeBase) return "UNSAFE:" + tree.unsafeStores.unsafeMethods.get(v - unsafeBase);
		return "S:" + siteName(tree.sites.get(v - tree.siteBase));
	}

	/**
	 * Returns a concise name for a graph node index.
	 *
	 * @param v the node index
	 * @return concise representation of the node
	 */
	String shortName(int v) {
		if (v < tree.siteBase) return v == 0 ? "ROOT" : v == 1 ? "GLOBAL" : tree.methods.get(v - 2).getSignature();
		int unsafeBase = tree.unsafeStores.unsafeBase;
		if (v >= unsafeBase) return "Unsafe store in " + tree.unsafeStores.unsafeMethods.get(v - unsafeBase).getSignature();
		AllocNode an = tree.sites.get(v - tree.siteBase);
		String n = siteName(an);
		int bar = n.indexOf('|');
		return bar < 0 ? n : an.getType() + "@" + an.getMethod().getDeclaringClass().getName() + "."
				+ an.getMethod().getName() + ":" + n.substring(bar + 1, n.lastIndexOf('|'));
	}

	/**
	 * Checks if an allocation node belongs to application code.
	 *
	 * @param an the allocation node
	 * @return true if the node is in an application class and is not a token
	 */
	static boolean isApp(AllocNode an) {
		return an.getMethod() != null && an.getMethod().getDeclaringClass().isApplicationClass() && !isToken(an);
	}

	/**
	 * Formats the top k entries from a frequency map into a summary string.
	 *
	 * @param m the frequency map
	 * @param k maximum number of top items to include
	 * @return formatted string of top entries
	 */
	static String top(Map<String, Integer> m, int k) {
		List<Map.Entry<String, Integer>> l = new ArrayList<>(m.entrySet());
		l.sort((a, b) -> b.getValue() - a.getValue());
		StringBuilder sb = new StringBuilder();
		for (int i = 0; i < Math.min(k, l.size()); i++)
			sb.append(i == 0 ? "" : "; ").append(l.get(i).getValue()).append(" ").append(l.get(i).getKey());
		return sb.toString();
	}
}
