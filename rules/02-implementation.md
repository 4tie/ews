# Implementation Rule

Before coding:
- identify the single ownership point for the change
- confirm no duplicate service or route already exists
- verify imports and storage helpers match the current app layout

When coding:
- make the smallest safe change that improves architectural integrity
- do not create duplicate logic in new files if an existing file can be extended
- do not leave mixed conventions behind in touched files
- keep route names, schemas, and storage paths internally consistent

After coding:
- list files changed
- describe what changed in each file
- state any contract changes
- state remaining risks or gaps