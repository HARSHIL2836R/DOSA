// O12: Thread confinement check.
// Static field shared is written by main and read concurrently by a background Thread runner.
// In the augmented call graph DAG, main and Worker.run() connect independently from SUPER_ROOT.
// Their LCA collapses to SUPER_ROOT, so shared remains GLOBAL -> HEAP.
public class O12 {
    static SharedState shared;

    public static void main(String[] args) throws Exception {
        shared = new SharedState();
        Thread t = new Thread(new Worker());
        t.start();
        t.join();
    }
}

class Worker implements Runnable {
    public void run() {
        if (O12.shared != null) {
            int v = O12.shared.val;
        }
    }
}

class SharedState {
    int val = 99;
}
