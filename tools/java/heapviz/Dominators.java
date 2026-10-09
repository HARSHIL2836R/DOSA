package heapviz;

import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.List;

public class Dominators {
	public static int[] dominators(int n, int[] off, int[] adj) {
		int[] postOrder = new int[n];
		Arrays.fill(postOrder, -1);
		int[] order = new int[n];
		int postOrderCount = 0;
		int[] stack = new int[n], childIterator = new int[n];
		boolean[] seen = new boolean[n];
		int stackPointer = 0;
		stack[stackPointer++] = 0; seen[0] = true; childIterator[0] = off[0];
		while (stackPointer > 0) {
			int v = stack[stackPointer - 1];
			if (childIterator[v] < off[v + 1]) {
				int w = adj[childIterator[v]++];
				if (!seen[w]) { seen[w] = true; childIterator[w] = off[w]; stack[stackPointer++] = w; }
			} else {
				stackPointer--;
				postOrder[v] = postOrderCount;
				order[postOrderCount++] = v;
			}
		}
		// predecessors among reachable nodes
		int[] poff = new int[n + 1];
		for (int v = 0; v < n; v++) if (postOrder[v] >= 0) for (int i = off[v]; i < off[v + 1]; i++) poff[adj[i] + 1]++;
		for (int v = 0; v < n; v++) poff[v + 1] += poff[v];
		int[] padj = new int[poff[n]];
		int[] pos = Arrays.copyOf(poff, n);
		for (int v = 0; v < n; v++) if (postOrder[v] >= 0) for (int i = off[v]; i < off[v + 1]; i++) padj[pos[adj[i]]++] = v;
		int[] idom = new int[n];
		Arrays.fill(idom, -1);
		idom[0] = 0;
		boolean changed = true;
		while (changed) {
			changed = false;
			for (int k = postOrderCount - 1; k >= 0; k--) {           // reverse postorder
				int node = order[k];
				if (node == 0) continue;
				int newDom = -1;
				for (int i = poff[node]; i < poff[node + 1]; i++) {
					int p = padj[i];
					if (idom[p] == -1) continue;
					if (newDom == -1) { newDom = p; continue; }
					int f1 = p, f2 = newDom;
					while (f1 != f2) {
						while (postOrder[f1] < postOrder[f2]) f1 = idom[f1];
						while (postOrder[f2] < postOrder[f1]) f2 = idom[f2];
					}
					newDom = f1;
				}
				if (idom[node] != newDom) { idom[node] = newDom; changed = true; }
			}
		}
		return idom;
	}

	public static boolean dominates(int n, int[] off, int[] adj, int d, int target) {
		if (d == target || d == 0) return true;
		boolean[] seen = new boolean[n];
		int[] q = new int[n];
		int h = 0, t = 0;
		q[t++] = 0; seen[0] = true; seen[d] = true;
		while (h < t) {
			int v = q[h++];
			if (v == target) return false;
			for (int i = off[v]; i < off[v + 1]; i++) if (!seen[adj[i]]) { seen[adj[i]] = true; q[t++] = adj[i]; }
		}
		return true;
	}

	public static int[] witness(int n, int[] off, int[] adj, int avoid, int target) {
		int[] parent = new int[n];
		Arrays.fill(parent, -2);
		int[] q = new int[n];
		int h = 0, t = 0;
		q[t++] = 0; parent[0] = -1;
		if (avoid >= 0) parent[avoid] = -3;
		while (h < t) {
			int v = q[h++];
			if (v == target) break;
			for (int i = off[v]; i < off[v + 1]; i++)
				if (parent[adj[i]] == -2) { parent[adj[i]] = v; q[t++] = adj[i]; }
		}
		if (parent[target] == -2 || parent[target] == -3) return null;
		List<Integer> p = new ArrayList<>();
		for (int v = target; v != -1; v = parent[v]) p.add(v);
		Collections.reverse(p);
		return p.stream().mapToInt(Integer::intValue).toArray();
	}
	public static int[] bfsParents(int n, int[] off, int[] adj, int src, int skip) {
		int[] parent = new int[n];
		Arrays.fill(parent, -2);
		int[] q = new int[n];
		int h = 0, t = 0;
		q[t++] = src; parent[src] = -1;
		if (skip >= 0) parent[skip] = -3;
		while (h < t) {
			int v = q[h++];
			for (int i = off[v]; i < off[v + 1]; i++)
				if (parent[adj[i]] == -2) { parent[adj[i]] = v; q[t++] = adj[i]; }
		}
		if (skip >= 0) parent[skip] = -2;
		return parent;
	}

	public static List<Integer> trace(int[] parent, int v) {
		List<Integer> p = new ArrayList<>();
		for (int x = v; x >= 0; x = parent[x]) p.add(x);
		Collections.reverse(p);
		return p;
	}
}
