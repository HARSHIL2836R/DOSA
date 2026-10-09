// O02: the StringBuilder.append pattern with an application class. Acc.add returns its
// receiver. One caller throws the chain's result away; the other stores it in a static.
// Spark gives add's return value one points-to set for every call, so the published Acc
// also appears as the value returned to the local caller.
public class O02 {
    static Acc kept;

    public static void main(String[] args) {
        local();
        published();
    }

    static void local() {
        Acc a = new Acc();          // A: dies when local() returns
        a.add(1).add(2);            // results discarded
    }

    static void published() {
        Acc b = new Acc();          // B: published through add's return value
        kept = b.add(3);
    }
}

class Acc {
    int sum;
    Acc add(int x) { sum += x; return this; }
}
