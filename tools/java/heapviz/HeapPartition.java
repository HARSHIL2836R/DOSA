package heapviz;

import java.io.BufferedWriter;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Paths;
import java.util.*;

import soot.SootField;
import soot.jimple.spark.pag.AllocNode;

/**
 * Partitions allocation sites and static fields into method-associated
 * memory arenas based on OWN, UP_k, and Scope LCA data.
 */
public class HeapPartition {

	public static class RegionPartition {
		final String regionName; // method signature or "GLOBAL"
		final List<Integer> ownSites = new ArrayList<>();
		final List<Integer> upSites = new ArrayList<>();
		final List<SootField> staticFields = new ArrayList<>();

		public RegionPartition(String regionName) {
			this.regionName = regionName;
		}

		public int totalAppSites(OwnershipTree tree) {
			int cnt = 0;
			for (int i : ownSites) if (SiteNaming.isApp(tree.sites.get(i))) cnt++;
			for (int i : upSites) if (SiteNaming.isApp(tree.sites.get(i))) cnt++;
			return cnt;
		}

		public int ownAppSites(OwnershipTree tree) {
			int cnt = 0;
			for (int i : ownSites) if (SiteNaming.isApp(tree.sites.get(i))) cnt++;
			return cnt;
		}

		public int upAppSites(OwnershipTree tree) {
			int cnt = 0;
			for (int i : upSites) if (SiteNaming.isApp(tree.sites.get(i))) cnt++;
			return cnt;
		}
	}

	final OwnershipTree tree;
	final Map<String, RegionPartition> partitions = new LinkedHashMap<>();
	final RegionPartition globalPartition = new RegionPartition("GLOBAL");

	public HeapPartition(OwnershipTree tree) {
		this.tree = tree;
	}

	public void partition(OwnershipResult b) {
		partitions.clear();
		globalPartition.ownSites.clear();
		globalPartition.upSites.clear();
		globalPartition.staticFields.clear();

		for (int i = 0; i < tree.sites.size(); i++) {
			AllocNode an = tree.sites.get(i);
			if (an.getMethod() == null || SiteNaming.isToken(an)) continue;
			String cls = b.cls[i];
			if ("OWN".equals(cls)) {
				String reg = b.region[i];
				partitions.computeIfAbsent(reg, RegionPartition::new).ownSites.add(i);
			} else if ("UP".equals(cls)) {
				String reg = b.region[i];
				partitions.computeIfAbsent(reg, RegionPartition::new).upSites.add(i);
			} else if ("HEAP".equals(cls)) {
				globalPartition.ownSites.add(i);
			}
		}

		if (tree.staticLiveness != null) {
			for (Map.Entry<SootField, soot.SootMethod> en : tree.staticLiveness.fieldCapturingMethod.entrySet()) {
				SootField sf = en.getKey();
				soot.SootMethod m = en.getValue();
				if (m != null) {
					partitions.computeIfAbsent(m.toString(), RegionPartition::new).staticFields.add(sf);
				} else {
					globalPartition.staticFields.add(sf);
				}
			}
		}
	}

	public void printSummary() {
		int methodRegions = 0;
		int totalAppCaptured = 0;
		int totalAppOwn = 0;
		int totalAppUp = 0;
		int totalScopedStatics = 0;

		for (RegionPartition p : partitions.values()) {
			int app = p.totalAppSites(tree);
			if (app > 0 || !p.staticFields.isEmpty()) {
				methodRegions++;
				totalAppCaptured += app;
				totalAppOwn += p.ownAppSites(tree);
				totalAppUp += p.upAppSites(tree);
				totalScopedStatics += p.staticFields.size();
			}
		}

		int globalApp = globalPartition.totalAppSites(tree);
		System.out.println("[ownership] heap partitions: " + methodRegions + " active method regions capturing "
				+ totalAppCaptured + " application sites (" + totalAppOwn + " OWN, " + totalAppUp + " UP), "
				+ totalScopedStatics + " method-scoped static fields; " + globalApp + " application sites in GLOBAL heap");
	}

	public void writePartitionFile(String[] names) throws IOException {
		try (BufferedWriter w = Files.newBufferedWriter(Paths.get(tree.outDir, tree.name + ".partition"), StandardCharsets.UTF_8)) {
			w.write("# region\tapp_total\tapp_own\tapp_up\tscoped_statics\tsites\n");
			List<RegionPartition> sorted = new ArrayList<>(partitions.values());
			sorted.sort((p1, p2) -> Integer.compare(p2.totalAppSites(tree), p1.totalAppSites(tree)));

			for (RegionPartition p : sorted) {
				int totalApp = p.totalAppSites(tree);
				if (totalApp == 0 && p.staticFields.isEmpty()) continue;
				List<String> siteNames = new ArrayList<>();
				for (int i : p.ownSites) if (SiteNaming.isApp(tree.sites.get(i))) siteNames.add(names[i] + "(OWN)");
				for (int i : p.upSites) if (SiteNaming.isApp(tree.sites.get(i))) siteNames.add(names[i] + "(UP)");
				w.write(p.regionName + "\t" + totalApp + "\t" + p.ownAppSites(tree) + "\t" + p.upAppSites(tree) + "\t"
						+ p.staticFields.size() + "\t" + String.join(";", siteNames) + "\n");
			}
			int globalApp = globalPartition.totalAppSites(tree);
			List<String> globalSiteNames = new ArrayList<>();
			for (int i : globalPartition.ownSites) if (SiteNaming.isApp(tree.sites.get(i))) globalSiteNames.add(names[i]);
			w.write("GLOBAL\t" + globalApp + "\t0\t0\t" + globalPartition.staticFields.size() + "\t"
					+ String.join(";", globalSiteNames) + "\n");
		}
	}
}
