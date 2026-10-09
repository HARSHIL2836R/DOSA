package heapviz;

import java.util.*;

import soot.*;
import soot.jimple.*;
import soot.jimple.toolkits.callgraph.CallGraph;
import soot.jimple.toolkits.callgraph.Edge;
import soot.jimple.toolkits.callgraph.ReachableMethods;

/*
 * Identity returns (ownership v0.1, design note §5.4).
 *
 * Spark gives a method's return value one points-to set for all its callers. For a method that
 * returns exactly one of its arguments, such as StringBuilder.append returning its receiver,
 * that set is every object ever passed in, and a caller that stores the result stores all of
 * them as far as Spark knows (corpus O02).
 *
 * This rewrites
 *     l = y.m(a, b)            to        y.m(a, b); l = (T) y
 * when every call-graph target of the call returns, on every path, the identity local of the
 * same parameter, with no other definition of that local. The rewrite is exact for pointers:
 * the result is that argument, so Spark loses nothing it could have known. Rounds repeat, because
 * a rewritten body can turn a method that returned a call result into one that returns a
 * parameter (bridge methods that call the covariant append).
 */
public class IdentityReturns {

	/** -1: not an identity return; 0: returns this; k + 1: returns parameter k. */
	static int returnedParam(SootMethod m) {
		if (!m.hasActiveBody()) return -1;
		Body b = m.getActiveBody();
		Map<Local, Integer> alias = new HashMap<>();
		Map<Local, Integer> defs = new HashMap<>();
		for (Unit u : b.getUnits())
			for (ValueBox vb : u.getDefBoxes())
				if (vb.getValue() instanceof Local) defs.merge((Local) vb.getValue(), 1, Integer::sum);
		for (Unit u : b.getUnits()) {
			if (!(u instanceof IdentityStmt)) continue;
			IdentityStmt is = (IdentityStmt) u;
			if (!(is.getLeftOp() instanceof Local)) continue;
			Local l = (Local) is.getLeftOp();
			if (defs.getOrDefault(l, 0) != 1) continue;
			if (is.getRightOp() instanceof ThisRef) alias.put(l, 0);
			else if (is.getRightOp() instanceof ParameterRef) alias.put(l, ((ParameterRef) is.getRightOp()).getIndex() + 1);
		}
		// single-definition copies of an alias are aliases too (x = r0; return x)
		boolean changed = true;
		while (changed) {
			changed = false;
			for (Unit u : b.getUnits()) {
				if (!(u instanceof AssignStmt)) continue;
				AssignStmt as = (AssignStmt) u;
				if (!(as.getLeftOp() instanceof Local)) continue;
				Local l = (Local) as.getLeftOp();
				if (alias.containsKey(l) || defs.getOrDefault(l, 0) != 1) continue;
				Value r = as.getRightOp();
				if (r instanceof CastExpr) r = ((CastExpr) r).getOp();
				if (r instanceof Local && alias.containsKey(r)) { alias.put(l, alias.get(r)); changed = true; }
			}
		}
		int k = -2;
		for (Unit u : b.getUnits()) {
			if (!(u instanceof ReturnStmt)) continue;
			Value op = ((ReturnStmt) u).getOp();
			Integer a = op instanceof Local ? alias.get(op) : null;
			if (a == null) return -1;
			if (k == -2) k = a; else if (k != a) return -1;
		}
		return k < 0 ? -1 : k;
	}

	static int rewriteAll(CallGraph cg, ReachableMethods rm) {
		List<SootMethod> ms = new ArrayList<>();
		for (Iterator<MethodOrMethodContext> it = rm.listener(); it.hasNext(); ) {
			SootMethod m = it.next().method();
			if (m.hasActiveBody()) ms.add(m);
		}
		int total = 0;
		for (int round = 0; round < 6; round++) {
			Map<SootMethod, Integer> ret = new HashMap<>();
			for (SootMethod m : ms) {
				Type t = m.getReturnType();
				if (t instanceof RefLikeType) ret.put(m, returnedParam(m));
			}
			int n = 0;
			for (SootMethod m : ms) {
				Body b = m.getActiveBody();
				List<Unit> units = new ArrayList<>(b.getUnits());
				for (Unit u : units) {
					if (!(u instanceof AssignStmt)) continue;
					AssignStmt as = (AssignStmt) u;
					if (!(as.getLeftOp() instanceof Local) || !(as.getRightOp() instanceof InvokeExpr)) continue;
					InvokeExpr ie = (InvokeExpr) as.getRightOp();
					int k = -2;
					boolean ok = true;
					for (Iterator<Edge> it = cg.edgesOutOf(u); it.hasNext() && ok; ) {
						Edge e = it.next();
						if (e.kind() == Kind.CLINIT) continue;
						Integer r = e.kind().isExplicit() ? ret.get(e.tgt()) : null;
						if (r == null || r < 0) ok = false;
						else if (k == -2) k = r;
						else if (k != r) ok = false;
					}
					if (!ok || k < 0) continue;
					Value arg;
					if (k == 0) {
						if (!(ie instanceof InstanceInvokeExpr)) continue;
						arg = ((InstanceInvokeExpr) ie).getBase();
					} else {
						if (k - 1 >= ie.getArgCount()) continue;
						arg = ie.getArg(k - 1);
					}
					if (!(arg instanceof Local)) continue;
					Local lhs = (Local) as.getLeftOp();
					InvokeStmt inv = Jimple.v().newInvokeStmt(ie);
					inv.addAllTagsOf(u);
					Value rhs = arg.getType().equals(lhs.getType()) ? arg : Jimple.v().newCastExpr(arg, lhs.getType());
					AssignStmt copy = Jimple.v().newAssignStmt(lhs, rhs);
					b.getUnits().swapWith(u, inv);
					b.getUnits().insertAfter(copy, inv);
					n++;
				}
			}
			System.out.println("[ownership] identity returns, round " + round + ": " + n + " calls rewritten");
			total += n;
			if (n == 0) break;
		}
		return total;
	}
}
