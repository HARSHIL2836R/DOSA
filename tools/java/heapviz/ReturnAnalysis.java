package heapviz;

import java.util.*;
import soot.*;
import soot.jimple.*;
import soot.jimple.toolkits.callgraph.Edge;

/**
 * Interprocedural return-parameter analysis.
 * Determines which method parameters a return value may derive from.
 */
class ReturnAnalysis {

	final OwnershipTree tree;

	/**
	 * Creates a new ReturnAnalysis bound to the given OwnershipTree.
	 *
	 * @param tree the enclosing OwnershipTree instance
	 */
	ReturnAnalysis(OwnershipTree tree) {
		this.tree = tree;
	}

	/**
	 * Returns the bitmask corresponding to parameter k (0 = this, k + 1 = parameter k).
	 *
	 * @param k the parameter index
	 * @return single-bit mask for parameter k
	 */
	static long bit(int k) {
		return 1L << k;
	}

	/**
	 * Which parameters a call's result may derive from, TOP if it may be something else.
	 *
	 * @param u the invoke unit
	 * @param ie the invoke expression
	 * @param d parameter derivation mapping for locals in the caller
	 * @return bitmask of parameter dependencies or TOP
	 */
	// TODO: The fuck is happening here?
	long callValue(Unit u, InvokeExpr ie, Map<Local, Long> d) {
		Iterator<Edge> it = tree.cg.edgesOutOf(u);
		if (!it.hasNext()) return OwnershipTree.TOP;
		long r = 0;
		while (it.hasNext()) {
			Edge e = it.next();
			if (e.kind() == Kind.CLINIT) continue; // Implicit call to static initializer. https://www.sable.mcgill.ca/soot/doc/soot/Kind.html
			if (!e.kind().isExplicit()) return OwnershipTree.TOP; // isExplicit: the call is due to an explicit invoke statement
			Long rp = tree.retParams.get(e.tgt());
			if (rp == null || (rp & OwnershipTree.TOP) != 0) return OwnershipTree.TOP;
			for (int k = 0; k < 63; k++) {
				if ((rp & bit(k)) == 0) continue;
				Value v;
				if (k == 0) {
					if (!(ie instanceof InstanceInvokeExpr)) return OwnershipTree.TOP;
					v = ((InstanceInvokeExpr) ie).getBase();
				} else {
					if (k - 1 >= ie.getArgCount()) return OwnershipTree.TOP;
					v = ie.getArg(k - 1);
				}
				r |= valueOf(v, d);
			}
		}
		return r;
	}

	/**
	 * Computes the parameter derivation mask for a given value.
	 *
	 * @param v the value to evaluate
	 * @param d parameter derivation mapping for locals
	 * @return derivation bitmask or TOP
	 */
	static long valueOf(Value v, Map<Local, Long> d) {
		if (v instanceof Local) return d.getOrDefault(v, 0L);
		if (v instanceof NullConstant) return 0;
		return OwnershipTree.TOP;
	}

	/**
	 * Parameter derivation of every local of m: flow-insensitive, least fixpoint.
	 *
	 * @param m the method to analyze
	 * @return map from locals to their parameter derivation masks
	 */
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
					else v = TOP();
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
					else v = TOP();
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

	private static long TOP() {
		return OwnershipTree.TOP;
	}

	/**
	 * Computes the parameter derivation mask for values returned by the given method.
	 *
	 * @param m the method being analyzed
	 * @param d parameter derivation mapping for locals
	 * @return derivation bitmask for returned values
	 */
	long returnsOf(SootMethod m, Map<Local, Long> d) {
		long r = 0;
		for (Unit u : m.getActiveBody().getUnits()) {
			if (!(u instanceof ReturnStmt)) continue;
			r |= valueOf(((ReturnStmt) u).getOp(), d);
		}
		return r;
	}

	/**
	 * Computes parameter derivation for method returns across all reachable methods.
	 */
	void computeReturns() {
		Map<SootMethod, Set<SootMethod>> callers = new HashMap<>();
		Deque<SootMethod> work = new ArrayDeque<>();
		for (SootMethod m : tree.methods) {
			if (!m.hasActiveBody()) { tree.retParams.put(m, OwnershipTree.TOP); continue; }
			tree.retParams.put(m, 0L);
			work.add(m);
			for (Iterator<Edge> it = tree.cg.edgesOutOf(m); it.hasNext(); )
				callers.computeIfAbsent(it.next().tgt(), k -> new HashSet<>()).add(m);
		}
		Set<SootMethod> queued = new HashSet<>(work);
		int rounds = 0;
		while (!work.isEmpty()) {
			SootMethod m = work.poll();
			queued.remove(m);
			rounds++;
			long old = tree.retParams.get(m);
			long r = returnsOf(m, derive(m));
			long nw = ((old | r) & OwnershipTree.TOP) != 0 ? OwnershipTree.TOP : (old | r);
			if (nw != old) {
				tree.retParams.put(m, nw);
				for (SootMethod c : callers.getOrDefault(m, Collections.emptySet()))
					if (c.hasActiveBody() && queued.add(c)) work.add(c);
			}
		}
		int top = 0, param = 0, none = 0;
		for (long v : tree.retParams.values()) { if ((v & OwnershipTree.TOP) != 0) top++; else if (v != 0) param++; else none++; }
		System.out.println("[ownership] returns: " + param + " methods return a parameter-derived value, "
				+ top + " may return something else, " + none + " return nothing; " + rounds + " method visits");
	}
}
