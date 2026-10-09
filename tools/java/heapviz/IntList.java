package heapviz;

import java.util.Arrays;

public final class IntList {
    int[] data = new int[1024];
    int count;
    /**
     * Appends an element to the list, growing the backing array if needed.
     * @param x the element to add
     */
    void add(int x) { if (count == data.length) data = Arrays.copyOf(data, count * 2); data[count++] = x; }
}