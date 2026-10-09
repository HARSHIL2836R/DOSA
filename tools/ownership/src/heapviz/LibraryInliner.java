package heapviz;

import java.util.*;

import soot.*;
import soot.jimple.*;
import soot.jimple.toolkits.callgraph.CallGraph;
import soot.jimple.toolkits.callgraph.Edge;
import soot.jimple.toolkits.callgraph.ReachableMethods;
import soot.jimple.toolkits.invoke.SiteInliner;
import soot.tagkit.AttributeValueException;
import soot.tagkit.BytecodeOffsetTag;
import soot.tagkit.Tag;

/*
 * Library inlining (design note 2026-09-24-Ownership-Trees.md §4.5, the context test of Phase 21).
 *
 * Spark gives a JDK allocation site one abstract object for every caller in the program, which is
 * where most allocated bytes are (Micro-Corpus-Log F20.5: LinkedList.listIterator alone is 41.5 %
 * of avrora's). Inlining a small JDK method into an application caller before Spark runs gives
 * each call site its own copy of the allocation: one level of call-site context, by rewriting
 * the code, as identity returns do.
 *
 * Rules: the container is a reachable application method; the call has exactly one explicit
 * call-graph target; the target is a JDK method with a body of at most maxUnits units that
 * allocates itself or through a call. Rounds repeat into the inlined code, up to `rounds` deep.
 * The rewrite preserves semantics, so the analysis stays sound; it only changes what Spark can
 * tell apart.
 *
 * Naming. An allocation that came in through inlining is named
 *     <container>#<call bci>><callee>@<call bci in callee>><callee 2>@...|<alloc bci>|<type>
 * which Flight Recorder frames rebuild from the allocating frame down to the first application
 * frame (alloc_weight.py). Soot's inliner copies each unit's tags, so an Origin tag put on the
 * JDK body before cloning leads each clone back to its original unit, whose call-graph edges
 * choose the targets of the next round.
 */
public class LibraryInliner {

	static final class Origin implements Tag {
		final Unit orig;
		Origin(Unit u) { orig = u; }
		public String getName() { return "heapviz.Origin"; }
		public byte[] getValue() throws AttributeValueException { return new byte[0]; }
	}

	/** Chain prefix of every unit created by inlining, in its container, and how many levels of
	 *  inlining it came through (counted separately: signatures contain '>' themselves). */
	static final Map<Unit, String> chain = new IdentityHashMap<>();
	static final Map<Unit, Integer> level = new IdentityHashMap<>();

	static boolean isJdk(SootMethod m) {
		String c = m.getDeclaringClass().getName();
		return c.startsWith("java.") || c.startsWith("javax.") || c.startsWith("sun.")
				|| c.startsWith("com.sun.") || c.startsWith("jdk.");
	}

	/** Methods whose body some copy came from. */
	static final Set<SootMethod> inlinedTargets = new HashSet<>();

	static final Map<SootMethod, Boolean> copyable = new HashMap<>();

	/**
	 * Whether copying t's body into container m keeps every call it makes resolving the same.
	 * Two kinds of call do not:
	 *  - a non-constructor invokespecial, when m's class is a strict subclass of the class the
	 *    call names: Soot then resolves it as a super call from m's superclass
	 *    (VirtualCalls.resolveSpecial), not to the method named. In any other class it resolves
	 *    to the method named, so LinkedList.listIterator(int)'s private checkPositionIndex call is
	 *    safe to copy into avrora's Medium$Receiver. (A first version refused every such call;
	 *    that also refused the iterator chain.)
	 *  - reflection: the Tamiflex log is keyed by the method making the reflective call, so a
	 *    copied Class.forName or Method.invoke loses its targets. Refused everywhere.
	 * Found when h2's reachable methods fell from 16,695 to 11,773 after one round
	 * (Micro-Corpus-Log F21.6).
	 */
	static boolean copyable(SootMethod t, SootMethod m) {
		if (!copyable.computeIfAbsent(t, k -> {
			for (Unit u : k.getActiveBody().getUnits()) {
				if (!(u instanceof Stmt) || !((Stmt) u).containsInvokeExpr()) continue;
				String dc = ((Stmt) u).getInvokeExpr().getMethodRef().getDeclaringClass().getName();
				if (dc.equals("java.lang.Class") || dc.startsWith("java.lang.reflect.")
						|| dc.startsWith("java.lang.invoke.") || dc.startsWith("sun.reflect.")) return false;
			}
			return true;
		})) return false;
		SootClass c = m.getDeclaringClass();
		FastHierarchy fh = Scene.v().getOrMakeFastHierarchy();
		for (Unit u : t.getActiveBody().getUnits()) {
			if (!(u instanceof Stmt) || !((Stmt) u).containsInvokeExpr()) continue;
			InvokeExpr ie = ((Stmt) u).getInvokeExpr();
			if (!(ie instanceof SpecialInvokeExpr)) continue;
			SootMethodRef r = ie.getMethodRef();
			if (r.getName().equals("<init>")) continue;
			SootClass d = r.getDeclaringClass();
			if (c != d && fh.canStoreType(c.getType(), d.getType())) return false;
		}
		return true;
	}

	static Unit origin(Unit u) {
		Tag t = u.getTag("heapviz.Origin");
		return t == null ? u : ((Origin) t).orig;
	}

	/** The call's bytecode offset. Soot tags `x = call(..)` with the offset of the store that
	 *  follows the invoke (avrora Medium$Receiver.earliestNewTransmission: invokeinterface at 17,
	 *  astore at 22, unit tagged 22), while Flight Recorder reports the invoke; the invoke
	 *  expression's own box carries the invoke's offset when Soot kept one. */
	static Integer bci(Unit u) {
		for (ValueBox vb : u.getUseBoxes()) {
			if (!(vb.getValue() instanceof InvokeExpr)) continue;
			BytecodeOffsetTag t = (BytecodeOffsetTag) vb.getTag("BytecodeOffsetTag");
			if (t != null) return t.getBytecodeOffset();
		}
		BytecodeOffsetTag t = (BytecodeOffsetTag) u.getTag("BytecodeOffsetTag");
		return t == null ? null : t.getBytecodeOffset();
	}

	/** The one explicit target of a call: from the unit's own edges once Spark has seen the copy
	 *  (after a re-run), otherwise from the JDK original's. */
	static SootMethod target(CallGraph cg, Unit u) {
		return cg.edgesOutOf(u).hasNext() ? single(cg, u) : single(cg, origin(u));
	}

	static SootMethod single(CallGraph cg, Unit u) {
		SootMethod t = null;
		for (Iterator<Edge> it = cg.edgesOutOf(u); it.hasNext(); ) {
			Edge e = it.next();
			if (e.kind() == Kind.CLINIT) continue;
			if (!e.kind().isExplicit()) return null;
			if (t != null && t != e.tgt()) return null;
			t = e.tgt();
		}
		return t;
	}

	/** JDK methods that allocate within `depth` levels of small JDK calls. Optimistic: a call
	 *  counts if any of its targets allocates, since a copy may later resolve to one target. */
	static Set<SootMethod> allocating(CallGraph cg, Collection<SootMethod> jdk, int maxUnits, int depth) {
		Set<SootMethod> a = new HashSet<>();
		for (SootMethod m : jdk)
			for (Unit u : m.getActiveBody().getUnits())
				if (u instanceof AssignStmt && ((AssignStmt) u).getRightOp() instanceof AnyNewExpr) { a.add(m); break; }
		for (int d = 1; d < depth; d++) {
			Set<SootMethod> next = new HashSet<>(a);
			for (SootMethod m : jdk) {
				if (next.contains(m)) continue;
				search:
				for (Unit u : m.getActiveBody().getUnits()) {
					if (!(u instanceof Stmt) || !((Stmt) u).containsInvokeExpr()) continue;
					for (Iterator<Edge> it = cg.edgesOutOf(u); it.hasNext(); ) {
						SootMethod t = it.next().tgt();
						if (a.contains(t) && t.hasActiveBody() && t.getActiveBody().getUnits().size() <= maxUnits) {
							next.add(m);
							break search;
						}
					}
				}
			}
			a = next;
		}
		return a;
	}

	/**
	 * One round of inlining. Round 0 inlines calls in the application methods' own code; later
	 * rounds inline calls inside code an earlier round brought in. OwnershipTree re-runs Spark
	 * between rounds, so a copied call is resolved against its own receiver: inside an avrora
	 * method, AbstractList.listIterator()'s call to listIterator(0) has one target, LinkedList's,
	 * where in the JDK original it has one per list class in the program.
	 */
	static int inlineRound(CallGraph cg, ReachableMethods rm, int maxUnits, int rounds, int round) {
		List<SootMethod> apps = new ArrayList<>(), jdk = new ArrayList<>();
		for (Iterator<MethodOrMethodContext> it = rm.listener(); it.hasNext(); ) {
			SootMethod m = it.next().method();
			if (!m.hasActiveBody()) continue;
			if (m.getDeclaringClass().isApplicationClass() && !isJdk(m)) apps.add(m);
			else if (isJdk(m)) jdk.add(m);
		}
		Set<SootMethod> alloc = allocating(cg, jdk, maxUnits, rounds - round);
		Map<String, String> opts = new HashMap<>();
		int failed = 0;
		{
			int n = 0;
			for (SootMethod m : apps) {
				Body b = m.getActiveBody();
				if (b.getUnits().size() > 4000) continue;
				for (Unit u : new ArrayList<>(b.getUnits())) {
					if (!(u instanceof Stmt) || !((Stmt) u).containsInvokeExpr()) continue;
					String prefix = chain.getOrDefault(u, "");
					if (round == 0 ? !prefix.isEmpty() : prefix.isEmpty()) continue;   // one level per round
					SootMethod t = target(cg, u);
					if (t == null || t == m || !isJdk(t) || !t.hasActiveBody() || !alloc.contains(t)
							|| t.getActiveBody().getUnits().size() > maxUnits || t.isSynchronized() || !copyable(t, m)) continue;
					int lv = level.getOrDefault(u, 0);
					if (lv >= rounds) continue;
					Integer cb = bci(u);
					if (cb == null) continue;
					for (Unit tu : t.getActiveBody().getUnits())
						if (tu.getTag("heapviz.Origin") == null) tu.addTag(new Origin(tu));
					String p2 = prefix + cb + ">" + t.getSignature() + "@";
					try {
						// No InlinerSafetyManager check: it guards bytecode the verifier would reject
						// (a private method called through invokespecial from another class). Nothing
						// here is emitted, and Spark resolves such calls statically either way.
						@SuppressWarnings("unchecked")
						List<Unit> added = SiteInliner.inlineSite(t, (Stmt) u, m, opts);
						if (added != null) for (Unit nu : added) { chain.put(nu, p2); level.put(nu, lv + 1); }
						inlinedTargets.add(t);
						n++;
					} catch (RuntimeException e) {
						failed++;
					}
				}
			}
			System.out.println("[ownership] library inlining, round " + round + ": " + n + " calls inlined, "
					+ failed + " failed, " + alloc.size() + " allocating JDK methods eligible");
			return n;
		}
	}
}
