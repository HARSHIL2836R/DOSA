// O13: Static field read conditionally on entry (recurrent state across calls).
// Method foo() is called repeatedly by runSession().
// Under legacy Scope LCA without intra-procedural liveness, foo() is the sole accessor,
// which would unsoundly bind counter to foo()'s activation frame.
// Under Theorem 4, counter is Live-In to foo() (read before write),
// so the capturing scope is lifted to runSession() (UP1 @ runSession).
public class O13 {
    static Counter counter;

    public static void main(String[] args) {
        runSession();
    }

    static void runSession() {
        foo();
        foo();
    }

    static int foo() {
        if (counter == null) {
            counter = new Counter();
        }
        counter.val++;
        return counter.val;
    }
}

class Counter {
    int val = 0;
}
