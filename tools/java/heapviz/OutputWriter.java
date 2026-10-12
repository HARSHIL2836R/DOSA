package heapviz;

import java.io.BufferedWriter;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Paths;
import java.util.*;

import soot.jimple.spark.pag.AllocDotField;
import soot.jimple.spark.pag.AllocNode;

/**
 * Handles formatting and writing analysis results and diagnostics to output files.
 */
class OutputWriter {

	final OwnershipTree tree;

	/**
	 * Creates a new OutputWriter bound to the given OwnershipTree.
	 *
	 * @param tree the enclosing OwnershipTree instance
	 */
	OutputWriter(OwnershipTree tree) {
		this.tree = tree;
	}

	/**
	 * Describes the edge that reaches v on the path: GLOBAL directly, a frame, or &lt;site type&gt;.&lt;field&gt;.
	 *
	 * @param path list of node IDs forming a path
	 * @return human-readable representation of the edge
	 */
	String via(List<Integer> path) {
		if (path.size() < 2) return "-";
		int p = path.get(path.size() - 2), v = path.get(path.size() - 1);
		if (p == 1) return "GLOBAL";
		if (p < tree.siteBase) return "frame";
		int unsafeBase = tree.unsafeStores.unsafeBase;
		if (p >= unsafeBase) return "Unsafe store in " + tree.unsafeStores.unsafeMethods.get(p - unsafeBase).getDeclaringClass().getName();
		AllocNode pa = tree.sites.get(p - tree.siteBase), va = tree.sites.get(v - tree.siteBase);
		List<String> fs = new ArrayList<>();
		for (AllocDotField f : pa.getFields())
			if (f.getP2Set().contains(va)) fs.add(f.getField().toString());
		Collections.sort(fs);
		return pa.getType() + "." + (fs.isEmpty() ? "?" : String.join("|", fs));
	}

	/**
	 * Writes the .ownwhy attribution file explaining why each HEAP site is reachable from GLOBAL or ROOT.
	 *
	 * @param g the ownership graph
	 * @param r the ownership result
	 * @param ord sorted array of site indices
	 * @param names array of formatted site names
	 * @throws IOException if file writing fails
	 */
	void attribute(OwnershipGraph g, OwnershipResult r, Integer[] ord, String[] names) throws IOException {
		attribute(g, r, ord, names, "", "B");
	}

	/**
	 * Writes the .ownwhy attribution file with custom suffix and label.
	 *
	 * @param g the ownership graph
	 * @param r the ownership result
	 * @param ord sorted array of site indices
	 * @param names array of formatted site names
	 * @param suffix file name suffix
	 * @param label label for console output
	 * @throws IOException if file writing fails
	 */
	void attribute(OwnershipGraph g, OwnershipResult r, Integer[] ord, String[] names, String suffix, String label) throws IOException {
		int[] pg = Dominators.bfsParents(tree.nNodes, g.offsets, g.adjacency, 1, -1);
		int[] pr = Dominators.bfsParents(tree.nNodes, g.offsets, g.adjacency, 0, 1);
		Map<String, Integer> byKind = new TreeMap<>(), byDetail = new HashMap<>(), byVia = new HashMap<>();
		try (BufferedWriter w = Files.newBufferedWriter(Paths.get(tree.outDir, tree.name + ".ownwhy" + suffix), StandardCharsets.UTF_8)) {
			w.write("# site\troot\tdetail\tvia\tlength\tpath\n");
			for (int i : ord) {
				if (!SiteNaming.isApp(tree.sites.get(i)) || !"HEAP".equals(r.cls[i])) continue;
				int v = tree.siteBase + i;
				List<Integer> path;
				String kind, detail;
				if (pg[v] != -2) {
					path = Dominators.trace(pg, v);
					String why = path.size() > 1 ? tree.builder.globalWhy.getOrDefault(path.get(1), "unlabelled:?") : "unlabelled:?";
					int c = why.indexOf(':');
					kind = why.substring(0, c);
					detail = why.substring(c + 1);
				} else if (pr[v] != -2) {
					// reachable only from ROOT's entries, and no method dominates: two stacks,
					// or two entry points, reach it
					path = Dominators.trace(pr, v);
					kind = "entries";
					detail = path.size() > 1 ? tree.naming.shortName(path.get(1)) : "?";
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
					ps.append(tree.naming.shortName(path.get(k)));
				}
				w.write(names[i] + "\t" + kind + "\t" + detail + "\t" + vi + "\t" + path.size() + "\t" + ps + "\n");
				byKind.merge(kind, 1, Integer::sum);
				byDetail.merge(kind + ":" + detail, 1, Integer::sum);
				byVia.merge(vi, 1, Integer::sum);
			}
		}
		System.out.println("[ownership] why HEAP (" + label + "): " + byKind);
		System.out.println("[ownership]   top causes: " + SiteNaming.top(byDetail, 8));
		System.out.println("[ownership]   top last edges: " + SiteNaming.top(byVia, 8));
	}

	/**
	 * Writes the .own summary classification file for all allocation sites.
	 *
	 * @param b result of borrow-rule analysis
	 * @param nv result of naive analysis
	 * @param ord sorted array of site indices
	 * @param names array of formatted site names
	 * @throws IOException if file writing fails
	 */
	void writeOwn(OwnershipResult b, OwnershipResult nv, Integer[] ord, String[] names) throws IOException {
		try (BufferedWriter w = Files.newBufferedWriter(Paths.get(tree.outDir, tree.name + ".own"), StandardCharsets.UTF_8)) {
			w.write("# site\tapp\tB.class\tB.region\tB.owner\tB.up\tB.recursive\tN.class\tN.region\tN.up\n");
			for (int i : ord) {
				if (tree.sites.get(i).getMethod() == null || SiteNaming.isToken(tree.sites.get(i))) continue;
				w.write(names[i] + "\t" + (SiteNaming.isApp(tree.sites.get(i)) ? 1 : 0) + "\t" + b.cls[i] + "\t" + b.region[i] + "\t"
						+ b.owner[i] + "\t" + b.up[i] + "\t" + (b.rec[i] ? 1 : 0) + "\t" + nv.cls[i] + "\t"
						+ nv.region[i] + "\t" + nv.up[i] + "\n");
			}
		}
	}

	/**
	 * Writes the .owntree dominator chain file for application allocation sites.
	 *
	 * @param b result of borrow-rule analysis
	 * @param ord sorted array of site indices
	 * @param names array of formatted site names
	 * @throws IOException if file writing fails
	 */
	void writeTree(OwnershipResult b, Integer[] ord, String[] names) throws IOException {
		try (BufferedWriter w = Files.newBufferedWriter(Paths.get(tree.outDir, tree.name + ".owntree"), StandardCharsets.UTF_8)) {
			for (int i : ord) {
				if (!SiteNaming.isApp(tree.sites.get(i))) continue;
				int v = tree.siteBase + i;
				StringBuilder sb = new StringBuilder(names[i]);
				if (b.idom[v] == -1) sb.append("\n    (unreachable)");
				else for (int x = b.idom[v]; ; x = b.idom[x]) {
					sb.append("\n    <- ").append(tree.naming.nodeName(x));
					if (x == 0) break;
				}
				w.write(sb.append("\n").toString());
			}
		}
	}

	/**
	 * Runs OwnershipGraph B with what-if switches: S (special sinks), P (phantom no-op), SP (both).
	 *
	 * @param b result of baseline borrow-rule analysis
	 * @param ord sorted array of site indices
	 * @param names array of formatted site names
	 * @throws IOException if file writing fails
	 */
	void whatIf(OwnershipResult b, Integer[] ord, String[] names) throws IOException {
		String[] labels = {"S", "P", "SP"};
		OwnershipResult[] rs = new OwnershipResult[3];
		for (int k = 0; k < 3; k++) {
			tree.builder.specialSinks = k != 1;
			tree.builder.phantomNoop = k != 0;
			OwnershipGraph g = new OwnershipGraph(tree);
			tree.builder.common(g);
			tree.builder.borrowFrames(g);
			rs[k] = tree.classify(g, labels[k]);
			if (k == 2) attribute(g, rs[k], ord, names, "-sp", "SP");
			summary(labels[k], rs[k]);
		}
		tree.builder.specialSinks = tree.builder.phantomNoop = false;
		try (BufferedWriter w = Files.newBufferedWriter(Paths.get(tree.outDir, tree.name + ".ownwhatif"), StandardCharsets.UTF_8)) {
			w.write("# what-if, not sound: S = Spark's special nodes keep no fields, P = phantom callees keep nothing\n");
			w.write("# site\tapp\tB.class\tB.up\tS.class\tS.up\tP.class\tP.up\tSP.class\tSP.up\n");
			for (int i : ord) {
				if (tree.sites.get(i).getMethod() == null || SiteNaming.isToken(tree.sites.get(i))) continue;
				StringBuilder sb = new StringBuilder(names[i]).append('\t').append(SiteNaming.isApp(tree.sites.get(i)) ? 1 : 0)
						.append('\t').append(b.cls[i]).append('\t').append(b.up[i]);
				for (OwnershipResult r : rs) sb.append('\t').append(r.cls[i]).append('\t').append(r.up[i]);
				w.write(sb.append('\n').toString());
			}
		}
	}

	/**
	 * Prints a summary of classification statistics for a result.
	 *
	 * @param label label of the analysis configuration
	 * @param r the ownership result
	 */
	void summary(String label, OwnershipResult r) {
		Map<String, Integer> c = new TreeMap<>();
		int app = 0, recOwn = 0;
		for (int i = 0; i < tree.sites.size(); i++) {
			if (!SiteNaming.isApp(tree.sites.get(i))) continue;
			app++;
			String k = r.cls[i].equals("UP") ? "UP" + (r.up[i] >= 3 ? "3+" : String.valueOf(r.up[i])) : r.cls[i];
			c.merge(k, 1, Integer::sum);
			if (r.cls[i].equals("OWN") && r.rec[i]) recOwn++;
		}
		System.out.println("[ownership] " + label + ": " + app + " application sites " + c + ", OWN in a recursive method "
				+ recOwn);
	}
}
