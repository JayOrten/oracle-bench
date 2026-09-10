- what is the purpose of the developer regression test? What is it checking, how does it factor in?

- One problem with the swe-bench ocntainers is that they are huge repos. This is alone is fine, but telling the models to just generate unit tests for this is not good or realistic. would probably be better if we could tell models to generate tests for the specific issue, without mentioning the issue?

- also, need to organize the output dir a lot more

- the second thing I want to think about is finding repos/data that are smaller/R&D repos. If swe-bench has that, that would be cool., But I think this will lean into pulling arbitrary repos and setting them up for the benchmark. The only problem is that we don't necessarily have good buggy/golden sets, we would have to manually find repos with issues that were fixed and do the same thing.
