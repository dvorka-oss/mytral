# MyTraL Task System

Overview of the current MyTraL task system:

```
      +-----------------------------------------------------------+
      |                Flask (Web Application)                    |
      |  (runs in the main thread of the Python process)          |
      |                                                           |
      |  +-------------------+   HTTP request   +--------------+  |
  -----> |  Route Handler    |----------------->|  Task Submit |  |
      |  |  e.g. upload GPX  |  calls executor  |  (executor.) |  |
      |  +-------------------+   submit()       +------+-------+  |
      |                                                |          |
      |  (polls for status)                            |          |
      |  +-------------------+  GET /status ---> |  Status      | |
      |  |  AJAX / API       |<------------------|  Query       | |
      |  +-------------------+   response        +------+-------+ |
      +-------------------------------|---------------------------+
                                      |
                                      v
      +-----------------------------------------------------------+
      |               ThreadTaskExecutor (singleton)              |
      |   +-------------------+   Worker pool (ThreadPoolExecutor)|
      |   |  submit(task)     |   max_workers = N (default 3)     |
      |   |  get_status()     |                                   |
      |   |  get_logs()       |                                   |
      |   +-------------------+                                   |
      |            |                                              |
      |            | creates a new worker thread                  |
      |            v                                              |
      |   +-------------------------------+                       |
      |   | _execute_task_wrapper(task)   |                       |
      |   |  - set status RUNNING         |                       |
      |   |  - call _create_task_instance |                       |
      |   |  - task_instance.execute()    |                       |
      |   |  - on finish:                 |                       |
      |   |      * write logs             |                       |
      |   |      * set status DONE/FAIL   |                       |
      |   |      * optional cache evict   |                       |
      |   |      * release per‑user lock  |                       |
      |   +-------------------------------+                       |
      +-----------------------------------------------------------+
                                      |
                                      v
      +-----------------------------------------------------------+
      |               Task Implementations (e.g.                  |
      |               GpxImportTask, FitImportTask, …)            |
      |   - receive: task entity, logger, log_callback            |
      |   - perform: I/O, conversion, dataset.save_activity()     |
      |   - periodically call task.check_cancellation()           |
      +-----------------------------------------------------------+
                                      |
                                      v
      +-----------------------------------------------------------+
      |                     Dataset / Cache Layer                 |
      |   +-------------------+      +---------------------------+|
      |   | JSONUserDataset   |<---->| InMemoryMytralCache       ||
      |   | (persisted JSON)  |      |  - _thread_safe_guardian  ||
      |   +-------------------+      |  - evict(user_id)         ||
      |          ^                   |  - user(user_id)          ||
      |          |                   +---------------------------+|
      |   +-------------------+                                   |
      |   | Cache Operations  | (cache_evict, cache_update_user_…)|
      |   +-------------------+                                   |
      +-----------------------------------------------------------+
```

Legend:

* Solid arrows = direct method calls / data flow
* Dashed arrows = periodic polling (AJAX) from Flask to executor
* “per‑user lock” ensures only one task per user runs at a time
* In thread based implementation all components live in the **same Python process**,
  sharing memory and locks.


