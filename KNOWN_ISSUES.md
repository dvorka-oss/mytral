# Known Issues

I know, I know, it's one man show for now, right? ;)



## Bugs

### fix(gear): 🐞 gear service intervals correctness

* **Description**: Gear service intervals calculation is ~80% used and tested. Thorought testing, especially around retirement / time service intervals must be performed as don't that frequently.



## Performance

### perf(frontend): ⚡ top calendar week navigation

* **Description**: The navigation is slooow as it's build on the frontend, but must be moved to the backend.

### perf(frontend): ⚡ top feed day navigation

* **Description**: The navigation is slooow as it's build on the frontend, but must be moved to the backend.

### perf(import): ⚡ Polar PPP import

* **Description**: I improved it from 25' to 17" on the test data, hope to make it ~9".



## Incomplete Features

### feat(metrics): ✨ TRIMP for HR-based activity data analysis

* **Description**: I did ~3 wibe & manually review & refactor rounds and there is at least one missing, I think that I'm gettting close.
* **PR**: https://github.com/dvorka-oss/mytral/pull/49

### feat(metrics): ✨ 3D IR model for power-based activity data analysis

* **Description**: I did ~1 wibe & manually review & refactor round, will need much more effort to carefully review the implementation against the paper, make it useful and valuable.
* **PR**: https://github.com/dvorka-oss/mytral/pull/49

### feat(predictions): ✨ Tab ICL based activity predictions

* **Description**: I did just initial implementation of the weight download, the predictions code which is there will be removed as I have completely different plans for predicting the activities.

### feat(agent): ✨ AI Coach

* **Description**: I had a lot of fun experimenting with the agent-based coach - personalities in particular, however, I need to manually review & write the functions which pull the data in a smart and effient way.


