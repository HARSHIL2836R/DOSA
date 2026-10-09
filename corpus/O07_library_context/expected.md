# O07: a JDK allocation shared by every caller

**Written before the run.** Tests library inlining (`-Downership.inlineLib=true`, Micro-Corpus-Log
Phase 21), the cheap stand-in for call-site context on library allocation sites.

## Sites

| id | site | what |
|---|---|---|
| L | `main`, `LinkedList` | the list |
| I | `LinkedList.listIterator(int)`, `ListItr` | one JDK site for every call to `listIterator` in the program |

`walk` and `keep` each call `l.listIterator(0)`. `LinkedList.listIterator(int)` checks the index
and returns `new ListItr(index)`: a small body with one allocation.

## Concrete ownership

`walk`'s iterator is held only by `walk`'s local `it` and dies when `walk` returns. `keep`'s is
stored in the static `kept`. Neither is held by the list: a `ListItr` points to its list, not the
other way round.

## Predicted result

| site | without inlining | with inlining |
|---|---|---|
| L | HEAP: `keep`'s iterator reaches L through `ListItr.this$0`, and the static holds that iterator | HEAP |
| I (the JDK site) | HEAP | no longer allocated from `walk` or `keep` |
| I inlined into `walk` | (does not exist) | OWN(walk) |
| I inlined into `keep` | (does not exist) | HEAP |

The inlined copies are named `<walk>#<call bci>><listIterator>@|<bci>|ListItr`.
