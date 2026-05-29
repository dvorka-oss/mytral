# AI Assisted Coding Designs

## Modus Operandi
New feature / enhancement / fix implementation:

1. Let copilot to build research .md, design .md, plan .md, ... to this directory
   and push it while the feature is being implemented.
2. Once you need GitHub review / * is implemented move .md files
   to `dvorka/mytral-skunkworks/vibe` where it is archived and/or actively used.

The reason why these documents must be moved is that online code review assistants tend
to measure PR size including the .md documentation and refuse the review if it has
too many lines. In other words, use .md files **locally** only.
