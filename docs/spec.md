# Spec for Oracle Bench

We are going to put together a framework for testing agentic harnesses on test/unit generation tasks.

First, familarize yourself with SWE-Bench and SWT-Bench, because we are going to be doing something similar to them here.

The basic idea is that we will have a repo of code, in two version. One version will be "buggy", including at least one issue that we know about, and the other version will be "golden", with that issue fixed. We want to be able to give an agent the buggy repo of code and tell it "generate unit tests for this code". It will generate tests, and then we will run those tests against the repository it saw AND a "golden" set of code. This will give us signal, hopefully, and whether the agent is able to navigate the oracle problem. The oracle problem is where LLMs may struggle to generate good oracles in tests if there are preexisting problems in the code. Ideally, the agents should detect the issue and make tests that fail. We are looking for cases where instead, the agent generates tests that purposefully all pass, even on the buggy code. We are looking for what kinds of programming problems, types of bugs, etc. current agents struggle with.

This is very similar to SWT-Bench, except what they did is adapt the SWE-Bench problems and then give the agent the repo AND the description of the issue. Meaning, they pointed out what the bug was. We want to see if the agent can detect and navigate the issue on it's own, which is a much more realistic and difficult test.

## Datasets

There are three sources of data I've thought about for this benchmark:

1. Synthetic code examples. Just generated small examples for testing pinpointed issues. I've already played around with this a bit in repos/oracle-bench-prototyping. I found that Claude doesn't struggle at all with these kinds of problems, at least the ones that it generates. So I think it will be much more important to rely on real world data.
2. Benchmark/dataset examples. So, there have already been several papers in this area that used datasets; most of these papers didn't use agents, they just use dplain LLMs and fed them the code. For part of this project, I'd like to use these same dataset and run them against agents, which also probably includes formalizing the dataset code into repositories that the agent can function on. Here are a few papers and the corresponding datasets they used that I would like to test on:

- TESTGENEVAL: A REAL WORLD UNIT TEST GENERATION AND TEST COMPLETION BENCHMARK - they created a benchmark called TestGenEval that's literally code extracted from SWE-Bench. Not that impressive IMO but hey it got accepted to ICLR. They ran two tasks...full file unit test generation and test completion. It looks to me like they don't compare buggy vs golden code sets, they just look at how well the generated tests pass. We might not care about this one since it doesn't quite match the oracle problem we are going for and it's jus tripping off SWE-Bench.
- Rethinking the Influence of Source Code on Test Case Generation - they test the oracle problem and use the following datasets: 1) HumanEval, 2) MBPP, 3) APPS, 4) BugsInPy. it looks like for some of these they manually create a bug set.
- Design choices made by LLM-based test generators prevent them from finding bugs - They use the Refactory dataset, which includes correct and buggy program versions.
- Understanding LLM-Driven Test Oracle Generation - THey use the Github Recent Bugs (GHRB) dataset. It looks like this dataset does have buggy and correct versions.
- TOGLL: Correct and Strong Test Oracle Generation with LLMs - This one uses OracleEval25, I don't think it has buggy/golden versions, but this is interesting because these are huge repos. SOunds like they also use somethign called Defects4J?
- Benchmarking LLMs for Unit Test Generation from Real-World Functions - They release a benchmark called UnLeakedTestbench, they also have PreLeakedTestbench. Probably want to use this one at some point.

Now, obviously, all these benchmarks are going to be a little different. We're going to actually dig into each one and look through what's provided and how we can utilize it uniformly in our overall harness flow. For instance, many of these don't have buggy and golden versions, at least not explicitely. So we may disregard them, or we can just run with them anyways to connect to previous work, I'm not sure yet. Righ tnow I just want to build a general framwork that makes adding these on easy.

ALSO should not here: each of these papers uses different processing steps/setups for what they are trying to do. So we will need to do work in adapting their method for parity while testing what we want to test.

3. Real repos. This is the direction SWE-Bench and SWT-Bench take, and it's the most realistic and obvious direction. The easiest thing to do is take SWE-Benchs setup with their repos in containers and just adapt them for the task we want to run. This is probably the first thing we should try. In addition, however, it would be great to be able to have the ability to setup any arbitrary repository for the task. We could get correct/buggy versions just by specifiying the tag/state/commit of the repo.

## Architecture

This is the architecture I want to run this benchmark with. It's very similar to how SWE-Bench works:

The agent harness should be contained within a docker container. In the past I created a very similar setup for this but I had the agent in one container and then the code and it's environment in a different container and then the agent operated on the shared code, and then the code was run in it's container. This was donw for security purposes. But, I think for this repo, we can have everything in one container. We just need to be able to do these things with the container:

- Setup the code as a repo in the container, either from the dataset or pulling from the real repo.
- Setting up the environment for the code so that it can be run.
- Setting up the environment for the agent so that it can run the code and do other things
- Setting up the harness for the agent
- Programmatically launching the agent by passing it a prompt and letting it run autonomously.

In my mind the most straightforward architecture for this benchmark is to have a way to define a configuration where you state which repos you want to run on, which harnesses to use, which models, what prompts, and then the benchmark iterates through these settings, lets the agents generate tests for each instance, and then runs the metrics we want on each one. This would mean we would setup and launch a container for each instance defined. I can just see this becoming expensive and slow and also taking up a lot of space on my harddrive lol, so I'm not sure if there's a cleaner faster way to do this. We could certainly setup base harness container that we build on top of. I'm aware SWE-Bench has been optimized to do some nice things so the containers are lighter and easier to work with.

## Evaluation

The simplest thing to do for now is:

1. Coverage, running coverage with the tests and the repo. This should be somewhat straightforward, just run of the mill coverage testing like you would manually do
2. Accuracy; I'm thinking we want to collect a confusion matrix of how many tests pass/fail against the buggy and golden versions of the code.

There are other things we can do but this is a good start.

# To start out

To start out let's just think about how to set things up to use the swe-bench/swt-bench repo tasks and get the basic pipeline flow down for launching the container, running the agent, and getting results

# Conclusion + notes

ANy gotchas you can think of? Anything that might be challenging? Idk if setting up the repos or using the SWE-Bench stuff is going to be tricky

Doing this could get very expensive fast if we are testing mutliple models on multiple harnesses across a whole bunch of repos. We'll just need to start slow and go from there when we are getting good signals

The ultimate goal here really is to have a benchmark for this problem, and test generation in general, that's like "the" benchmark for this kind of task, that's best case. Which is why I want to cover both datasets and real repos.

Let's brainstorm and flesh this out into a full detailed plan. I want to dig into what the specific implementation will look like before we code anything

Notes:

- You make good points about annotating instances with what kinds of problems they. I anticipate we will do this post-hoc; i want to run the benchmark across a bunch of repos/data, see where the agents struggle, and then analyze the specific data. It will not be tractable to do this all before hand
- Th eultimate scenario I am trying to test is when a developer has a repo they are working on, and it doesn' thave tests, so they just tell the agent "generate tests for this repo". Thats what we are tyring to replicate, BUT I think we will have to still do some targeted investigation on specific types of issues/scenarios. This will be after we have identified them though.
- yeah so one thing we want to catch is if the agent reaches out to the internet to try and find the solution to the problem, like looking at the repo itself. This is such a specific kind of cheating though that I think we could catch it with checks.
- You're right that we should remove any other hitory that might reveal the problem. But this might be very hard to do. So let's think about this later after we have initial signal
- I'd like you to put together an implementation plan. This should be split into multiple stages that build on each other, the first or first few should build an initial mvp that covers the full pipeline so we can test and get initial signal, and then we'll add more features. You have a lot of notes on validation and stuff that I think are really good but I don't want to dive into that prematurely
- your prposed metrics are a little confusing to me, I think they just have poor names. But yeah, i think you'r ejust reinventing my confusion matrix idea. Of course we'll dig into it a little deeper than that.
- yes we will want to test different version of coverage.
- exposing discarded tests fromt he agent is an interesting idea but not relevant righ tnow, we will not worry about that until later.
