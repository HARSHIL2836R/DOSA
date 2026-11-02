// O10: Re-entrant controller method invoked repeatedly in a loop.
// Static field state is ephemeral within each invocation of process().
// Under Scope LCA, process() dominates its own accesses, so state is captured by process() (OWN).
public class O10 {
    static TaskState state;

    public static void main(String[] args) {
        runSession(3);
    }

    static void runSession(int n) {
        for (int i = 0; i < n; i++) {
            process(i);
        }
    }

    static int process(int id) {
        state = new TaskState(id);
        int res = state.compute();
        state = null; // nullified before return
        return res;
    }
}

class TaskState {
    int id;
    TaskState(int id) { this.id = id; }
    int compute() { return id * 2; }
}
