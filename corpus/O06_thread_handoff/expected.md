# O06: a second thread

**Written before the run.** Tests the thread rule: parameters of a method started on another
thread (Soot's `THREAD`, `EXECUTOR`, `FINALIZE` edges) hang off the global root, not off the
starting frame.

## Bytecode facts

| id | site | what |
|---|---|---|
| S | `main` bci 0, `Box` | passed to `Worker.<init>` at 13, stored into `Worker.b` |
| W | `main` bci 8, `Worker` | `start` at 18, `join` at 22 |
| M | `main` bci 25, `Box` | |
| K | `main` bci 34, `Item` | stored into M at 41 |
| P | `Worker.run` bci 0, `Item` | stored into the shared Box at 13 |
| J | `Worker.run` bci 16, `Item` | |

## Concrete ownership

While the worker runs, S and W are reachable from both threads' stacks, so no single frame
dominates them. P is reachable through S. J is held only by the worker's `run` frame. M and K
belong to main.

## Predicted result

| site | B (v0) | truth |
|---|---|---|
| S | HEAP | HEAP |
| W | HEAP | HEAP |
| P | HEAP | HEAP |
| J | OWN(run) | OWN(run) |
| M | OWN(main) | OWN(main) |
| K | OWN(main) | OWN(main) |

W also reaches the heap through the JDK: `Thread.start` adds the thread to its `ThreadGroup`,
which Spark reaches from its special main-thread node.
