// O05: recursion. build() allocates tree nodes in every activation and returns them up, so
// they all die when main returns. count() allocates a scratch Counter in every activation
// that dies with that activation, but a method that calls itself has many activations, and
// the analysis can only name the method.
public class O05 {
    public static void main(String[] args) {
        TreeNode t = build(3);      // T: built in build, owned by main
        int n = count(t);
    }

    static TreeNode build(int d) {
        TreeNode n = new TreeNode();
        if (d > 0) {
            n.l = build(d - 1);
            n.r = build(d - 1);
        }
        return n;
    }

    static int count(TreeNode n) {
        if (n == null) return 0;
        Counter c = new Counter();  // C: scratch, dies with its own activation
        c.v = 1 + count(n.l) + count(n.r);
        return c.v;
    }
}

class TreeNode { TreeNode l, r; }
class Counter  { int v; }
