# Work Log

## **Work Log**

**5/17** 

**10:00**

| Here’s the work trial question: build a prototype of a system that helps a researcher keep up with relevant research happening in their field, so that they are well informed. This problem is deliberately large and open-ended. Please imagine you’re building this for safety researchers around you, and make whatever assumptions seem correct to you. Deliverables: \- a working codebase with instructions that we can run to play around with your prototype (we will read the code). Use any tech you want.  \- a short doc describing your solution, and how you made various choices \- screenshots or video of a user journey Assume this is for a single user only (no multi user support needed). Please let me know if you have any questions, although you’re encouraged to make your best guess assumptions about what solving this problem in reality would actually be like, note those, and proceed. |
| :---- |

Clarifying q’s for Vikrant: 

| Hey Vikrant, Thanks\! Just confirming, do I have 48 hours to work on this question? So should I submit it 5/19 at 8 am PST? Best, Caden |
| :---- |

Initial thoughts: 

- I use deep research to papers for citations, but it’s not that great for finding new / interesting ideas. It mostly finds what I’d find if I looked up what I wanted in 10 different ways and skimmed the first page of Google.  
- I like Twitter as a resource for finding interesting papers.   
  - Occasionally I’ll find a post with 10-50 likes launching a paper.   
  - Twitter more often surfaces interesting papers by referral, e.g. people I know repost or talk about it.  
  - Still a good amount of papers lost.   
- Friends have mentioned various paper mailing lists as great ways to find new papers.   
  - The Google Scholar mailing list.  
  - I think there was another one, I forget the name though.   
- Lots of these thoughts above are largely related to filtering for \*interesting papers\* rather than “keeping up with relevant research” as the prompt suggested. Thoughts here:   
  - I keep up with relevant research again through Twitter, it’s a great word of mouth for what’s important among researchers I respect.  
  - Idea: Look into existing recommendation algorithms. E.g. Twitter’s was recently updated and rereleased yesterday.   
  - Idea: An LLM based recommendation system. Keeps some memory system of natural language propositions about what the user believes, uses this to filter for relevant research. The memory system is updated as the user navigates more papers, maybe leaves some light up / down vote feedback for the system.  
  - Idea: Could be some neat stuff around \*inline\* citations. For example, an LLM generated summary claims idea X is interesting and links to the direct line in ArXiv where this idea is stated.   
  - A system I really love is Cognition’s DeepWiki. I think there are some similar systems here, like [Codemaps](https://cognition.ai/blog/codemaps). DeepWiki is essentially fast codebase search, launches a bunch of small LLMs in parallel across grep matches and summarizes their findings. (I think)

Sort of filtering through my initial thoughts, I think there are a couple dimensions here: 

1. Some primary use cases:   
   1. Lots of ML papers come out every day. How do we surface relevant papers to a researcher?  
   2. A researcher has been locked-in on a project and is out of date on recent research. How do they find relevant papers they missed?  
2. How do we make sure these relevant papers are interesting?  
3. How do we do this in a way that’s really easy for a researcher to skim and ingest lots of information?

**10:30**

Spent some time going through my initial takes and trying to pull apart the important questions. Current plan for the next 48 ish hours: 

- 5/17  
  - Morning: Plan, think through what this system should look like. Final deliverables:   
    - Mock user stories  
    - Key questions to address  
    - Researched approach  
    - Some rough wireframes  
  - Afternoon: v1 of the solution   
- 5/18   
  - Evening: Create the writeup, video demo of the solution  
- 5/19  
  - Morning: Clean up the code, get everything presentable.

*Existing work in this space*

Will spend some time looking through existing tools for keeping up with research. 

AlphaXiv  
[https://www.alphaxiv.org/](https://www.alphaxiv.org/)

![][image1]

Onboarding looked like: 

- Select Subject: I selected a subject: AI, CS, Physics, etc. I was only able to select a single subject though, and couldn't select both AI and CS.  
- Select Topics: Some search bar with lots of badges related to the field. I entered “Mechanistic Interpretability”.  
- Like Papers: I’m on this screen where I need to like or skip papers that it’s presenting me.  
  - NOTE: Kind of annoying that I can’t open the paper or expand and read the entire abstract. I have to copy the paper title into Google and skim it.   
  - NOTE: Also not clear how they’re presenting interesting papers. I’ve clicked through like 3 or 5 and they’re all about reasoning, and there’s one paper that’s not even MI?

![][image2]

Once I’ve liked a paper there’s no way for me to see what I’ve liked. Only to reset all likes. Also it looks like the paper list reloads after I’ve liked a paper, so there’s no way for me to navigate back to a paper I previously liked.

![][image3]

Two suggestions were actually pretty cool. I think I’m the exact target audience for this tool, I haven’t done the greatest job keeping up with AI papers recently. 

![][image4]

The paper area has some nice tools: 

Ingestion wise: 

- Audio reading of the paper  
- An LLM generated blog post  
  - NOTE: Thought this was only okay. Super verbose AI generated summary, would prefer something like a list of core claims in the paper and direct links to those claims. Also curious what an analogy would be like to [Codemaps](https://cognition.ai/blog/codemaps). Rather than a citation just linking to the claim, it would be cool if an LLM would bring up the entire link chain which led to that claim. I imagine this would get a bit hairy if there’s a \*lot\* of evidence across the paper to support some claim.   
    - Hesitantly, I think this could be cool represented as a network. But at the same time, I’m not a huge fan of network representations for perusing data, and I often find it more useful to be given a set of filters I can trim and just an ordered list of results.

Recommendation wise:

- Global comment section  
- Area to keep personal notes  
- Similar papers list

Litmaps  
[https://app.litmaps.com/](https://app.litmaps.com/)

![][image5]

I looked up “mechanistic interpretability” and got a list of matches.

- NOTE: Should look into whether there’s a big, updating dataset of ArXiv papers?  
  - Looks like they provide a couple different search engines: Google Scholar, Semantic Scholar, and their own Litmaps search engine.

![][image6]

Pretty similar to connected papers? They just have an axis for the network graph. The recommended papers aren’t that great. 

- NOTE: For being up to date, I’d prefer to see recent papers that cite this paper. However, interesting recent papers either don’t show up (e.g. [this](https://arxiv.org/abs/2507.21509)) or just don’t have enough citations to show up (e.g. [this](https://arxiv.org/abs/2605.02087)). 

ArXiv Labs  
[https://info.arxiv.org/labs/showcase.html](https://info.arxiv.org/labs/showcase.html)

Lots of other stuff from ArXiv labs.

![][image7]

Cool. Pretty relevant approach for keeping up with relevant research happenings in a field.

![][image8]

I see this thing pretty often.

*Some takes after going through the above things*

- There’s a lot of stuff on visualizing citations, connected papers. These tools seem relevant for discovering papers to cite, but they aren’t great for keeping up with new, interesting papers.  
- Could make some all in one platform:   
  - Daily summary linking to relevant / interesting papers.  
  - An actual \*feed\* of papers to scroll through.  
  - A box for deep research style questions.

**12:00**

At this point I have a good sense of existing work and the important questions in this area. Just going to think through some mock user profiles, outline the important questions, and start thinking about a concrete solution.

I think the most important questions at the moment are: 

- How do we surface relevant papers for a researcher?   
- How do we present information in a way that’s easy for the researcher to digest?

*User Profiles*

- Likes to read through ML papers daily, wants to spend less time   
- Lots of ML papers come out every day. How do we surface relevant papers to a researcher?  
- A researcher has been locked-in on a project and is out of date on recent research. How do they find relevant papers they missed?

**12:15** 

Going on a walk outside for a bit to think about things.

**12:45**

Back\! I also found a different place to work, it was a bit distracting at home.

Here’s the work trial question: build a prototype of a system that helps a researcher keep up with relevant research happening in their field, so that they are well informed.

Super useful walk, couple things I want to emphasize: 

1 \- I’m building this tool for a single user rather than a multi user platform. I think LLMs can be super useful for getting papers and way more efficient than ML engagement algorithms. 

2 \- I think we can do a lot around “keeping up” and being “well informed”. A feeling I often have with existing recommendation algorithms is: 

- The research isn’t super relevant. Even if the research is related to something I’ve worked on, it’s only very broadly. For example, being interested in “mech interp” and the algorithm suggests a bunch of papers on MI for reasoning. Even if the algorithm is more granular like “circuit discovery”, I might have nuances like, “circuit discovery NOT benchmarks” which is hard to pick up on.

Here’s what I’d like to build:

- **Onboarding.** Current onboarding processes are super light. They might pull in a researcher’s past papers. They could go a step deeper and ask them to like 5 papers. We could get a lot more information up front by:   
  - Asking the user to describe their current interests, research directions. Transcribe their voice to text, and extract natural language propositions.   
  - Ask the user to dump in more resources like job talk slideshows, maybe a Google doc with working notes for their experiments, codebases.   
  - Also current onboarding workflows suck.   
- **Deep information.** Current recommendation algorithms just keep pretty light metadata about users like liked posts, engagement, etc. We can go a step further:   
  - Keeping natural language propositions about the user’s interests.   
  - Current recommendations are offered to the user with no visibility on \*why\*. It’s frustrating to get an ML newsletter with a bunch of irrelevant suggestions and feel like you’re fighting the algorithm to get interesting papers. We could provide reasons for why every paper is recommended to a user, and the user can engage with this reasoning to provide targeted feedback to the algorithm. E.g. this [product](https://imbue.com/product/bouncer) from Imbue.  
- **Tracking beliefs.** The most interesting papers are often just along directions a researcher is thinking about. It could be cool to track “hypotheses”.  
  - Here’s the setup:   
    - When a user engages with papers, they can leave notes / thoughts.   
    - There’s also a feature to decompose papers into a claim / warrant graph.   
    - The user’s feedback is sorted into positive / neutral / negative feedback.  
    - This feedback is kept as a global list of “hypotheses”.  
    - When surfacing relevant papers, papers are sorted by relevance to these “hypotheses”.  
  - Here’s an example workflow:   
    - The user onboards and the system shows them papers about LLM judges.  
    - The user skims a paper and highlights a claim that LLM judges are unreliable.   
    - This is a \*negative\* hypothesis.   
    - On the next day of new papers, run an LLM judge to find papers related to this hypothesis. Group them into positive / neutral / negative.   
    - On the user’s daily dashboard, they see these papers clustered under the hypothesis.  
    - They can click “not interested” to delete this as a hypothesis if they’re not interested in papers about this topic.  
    - They can engage and keep seeing relevant papers.  
  - I think this is super relevant for building \*understanding\*, deeper than what paper tracking like Zotero or a Notion database could record.  
  - We could represent this understanding as a graph\!  
- **Idea maps.** Reading papers is time consuming, and LLM generated summaries are pretty bad. Rather than providing a general “summary” we could ask an LLM to decompose a paper into its core claims / warrants.   
  - The user can click on a claim and view all the supporting evidence. For example, on a paper for LLM judging the user might expand a claim on “LLM judges are unreliable”. They’d get the supporting evidence of relevant figures, experiments, and sources cited in the background section.   
  - Underlying all of this might be a single idea graph, don’t look up warrants on the fly when the user expands a claim.

Other considerations: 

- Vikrant specifically mentions “staying informed”. I think there are two parts to this:   
  - A person might want to be **broadly informed** of cool papers in their field that everyone is talking about. I think this is a multi user question, and out of scope. Down the line, we could simply scrape Twitter sentiment.   
  - A person wants to be specifically informed of papers in their specific subfield, or subfields they’re interested in.

Here’s a good framing for what I’m thinking about. Currently, platforms represent user interest as vaguely defined engagement, paper likes. I think the right representation is a hypothesis. What hypotheses are people interested in? This is out of scope, but it could make for a really interesting platform. Here’s what a platform would look like.

1. Users join and seed their account with all the research directions they’re thinking about.   
2. They get papers directly related to specific questions they’re investigating.  
3. They form new hypotheses by engaging and reading new papers.  
4. Over time, they get a graph of hypotheses. An LLM could look at their hypothesis and try to group related hypotheses and create new connections.   
5. As a community, it could be cool to share hypothesis graphs with friends and see trending hypotheses in a field. 

**1:30**

I’m super excited about this direction\! Going to plop all my notes into Claude and see if it has any feedback so far. Then start hammering things into a tool / interface. 

Okay, so the main feedback is some ambiguity on scope. 

- To be clear I am not focusing on the use case where users are 1-2 months out of date and want to get a general scope of what’s going on in the field. They should use deep research for that. This is more for a researcher who is engaged on a consistent basis and wants to stay informed. E.g. a researcher who scrolls Twitter or is signed up for a paper newsletter.   
- I am also not focusing on the idea of “generally staying up to date”. I’m more interested in 

Some other suggestions on baselines. How can I measure whether my system is actually providing uplift? Some ideas here: 

- I should maybe ask Vikrant whether I can do user interviews. Since talking to researchers is very relevant to the team, I wonder if he’d be okay with this. This request is a bit odd for an independent work trial though.  
- Baseline against other platforms. A method I could do here beyond “vibes” is eliciting preference distributions from forced choice questions; see [this paper](https://arxiv.org/abs/2502.08640), for example.  
  - I could run a similar search on my prototype versus another platform like AlphaXiv, Google Scholar’s chatbot, deep research results. Then see which search results I prefer.

**1:50**

Spent an hour writing a plan for impl, is in the tab [Plan v1]().

**2:50**

Have been mulling over the plans above and thinking for awhile, but finally created a GH repo lol. 

Created a Plan v2 tab which is a copy of v1 but with some changes and emphasis on certain features. Specifically: 

- Rather than showing a daily summary of relevant papers and sorting by the number of citations, I should sort in a diff based manner. Something like, “here’s what shifted in your hypothesis space today”  
- Some framing I dropped which I think I should put more emphasis on is new papers refuting / supporting claims. Surfacing papers which refute a hypothesis the user has seems way more useful than, “here are a couple of generally related papers”.  
- Not sure if the graph framing is strong, and it might not be super relevant. I don’t think it offers too much of an advantage over just a list of hypotheses.   
  - I think we could include some relations though. Like there could be a graph, but I don’t want to force it. E.g. if the user comments on a paper that was surfaced as part of a hypothesis, don’t immediately make it a child of the other hypothesis. Maybe just make it a dropdown or something.   
    - Rather than forcing the user to write comments, I think automatically having an LLM extract claims is super useful.  
- Should have some notes on hypothesis maintenance.   
- I also don’t only want to run LLM judges leaf hypothesis. Non leaf hypotheses are still relevant, just a parent hypothesis of another. Could be an issue of just having a lot of hypotheses though. 

I also think getting the idea map for a paper correct is super important. This is how we make it feasible for researchers to actually read papers\! I think this is an important part of the “keeping up” part of Vikrant’s wording. Lol, this plan is becoming more and more like Docent… woah\!

There’s one issue with the current system that’s slightly out of scope. Specifically, sometimes the user might write some hypothesis that has evidence in papers from previous days, but searching over prior papers is out of scope. I guess I’m a bit uncertain what ArXiv rate limits are and how much storage this would involve or else I would do this.

Here’s how I think hypothesis should work:

- The user writes a hypothesis which is a claim, e.g. “LLM as a judge evaluation is unreliable”   
- Search looks for papers which support or refute the claim and show them in the summary. It should also explain why the paper supports / refutes, as best as it can from the abstract.  
- The user can click on evidence and start an idea map generation \+ warrant chain search in the paper. They can upvote or downvote evidence here.

From within a paper, the user can write more claims, or deeper claims. E.g. “LLM as evaluation is unreliable because LLMs are overconfident and uncalibrated”. 

Stepping back for a second, does this system help users keep up with research in their field and stay informed? 

- Keep up, yes. I think this hypothesis search system is great.   
- Stay informed, I’m not sure. I guess, if the user is interested in SAEs, all papers might be about SAEs but not broadly about mech interp or AI safety.  
  - Here, I think it could be useful to have two layers. A topic layer, where the user is interested in general topics. And then a hypothesis layer, where the user sees relevant research for their interests.  
  - I guess, staying informed has the same problem of how does the user keep up with topics which are broad and have many matches and lots of papers which could be dense.   
    - This sort of presents a reranking problem, where the user has general topic interests, and we want to show papers sorted by relevance to their current interests.

Since staying generally informed is useful, I might try something like. The user can add different natural language filters to the daily papers: 

- Claims, which are things the user believes. The model will find evidence to support / refute these claims  
- Questions, which are things the user wants to understand. The model will find relevant papers and claims in the abstracts  
- Topics, which are general areas the user is interested in. The model will find relevant claims in the abstract.

**3:30**

Starting to code v1\!

Moved an updated plan with the notes above into [Plan v2](). One thought is, I could pretty easily make it possible to search abstracts in the past by just expanding the start date for looking through arxiv papers.

I imagine that things could get a bit crowded. E.g. if the user doesn’t clear their filters and they have like 100 that are run every day. 

The user’s interests might change pretty often, i guess being able to say “not interesting to me anymore” on the home page is super important for managing the \# of filters.

**Random**

Could probably backtest whatever recommendation approach I do. 

1. Get all ML papers released in the last 3 or 4 months.  
2. Start from the first day, with about a month of information in context  
3. Select interesting categories, show recommendations to the user

—.

I wonder if I could have LLMs test this lmao. Like they give feedback to the system, I try to maximize their surprise when seeing new papers or something.

—

This feels somewhat similar to working on scalable oversight lol. Given a lot of papers that come in every day, how do I surface the relevant and interesting ones for human review.

—

LLM as a judge papers I’ve been meaning to read and might use for this:

- [https://arxiv.org/abs/2605.06235](https://arxiv.org/abs/2605.06235) (OBLIQ-Bench)  
- [https://arxiv.org/abs/2508.21762](https://arxiv.org/abs/2508.21762) (Reasoning Intensive Regression)  
- [https://arxiv.org/abs/2512.17267](https://arxiv.org/abs/2512.17267) (AutoMetrics)

**—**

Cleaning up the idea graph: 

- [https://platform.claude.com/docs/en/managed-agents/dreams](https://platform.claude.com/docs/en/managed-agents/dreams)  
- [https://github.com/OpenAnonymity/nanomem](https://github.com/OpenAnonymity/nanomem)

**—**

Bayesian surprisal metric for “interestingness”   
[https://allenai.org/papers/autodiscovery](https://allenai.org/papers/autodiscovery)

I’ve been reading some AI for science papers recently and I like this paper using Bayesian surprise as reward for MCTS. I want to build this idea where: 

- LLM keeps natural language propositions over what the user finds interesting.  
- Gives a prior on whether the user would find the paper interesting.  
- The user gives a posterior by upvoting / downvoting various claims that the LLM surfaces with citations from the paper.

I think this might just be a nerd snipe for a way simpler recommendation algorithm.

# Plan v1

Speccing out a bit how I’d like to build things: 

- Onboarding flow \-\> user interests  
- User interests \-\> graph  
- Graph \-\> surfacing interesting papers  
- Surfacing interesting papers \-\> summary  
- Papers \-\> tools for reading / engaging with the paper  
- Idea merging

*\*Onboarding flow \-\> user interests\**

Returns: some initial graph of user interests. 

V1

- Lets just start with a simple, drop text description of research interests in

V2

- Support dropping in files up to a size limit. File types:   
  - PDF format. This will encapsulate google docs, powerpoint, google slides, etc.  
  - Speech. Allow for audio transcription on the browser, speech to text  
  - Folders or files up to 5 mb. Just spin up an LLM in the background to explore it and the experiments that are being run. 

*\*Graph \-\> surfacing interesting papers\**

V1

- Every day, pull all the ML/AI papers off ArXiv   
- Run an LLM judge over their abstracts  
- Return relevant papers

How I think search should work:

1. Run an LLM judge. Either:  
   1. Run a judge for each leaf on the idea graph  
   2. Run a single judge with a rubric that includes all the leaves on the idea graph  
2. Given the list of papers and their corresponding categories, return the papers sorted by their number of citations?  
   1. Each search result card should:   
      1. Include a dropdown which explains why the paper was returned, e.g. what idea it related to and how

V2

- Figure out whether it's feasible to judge the entire paper?

NOTE: check if this arxiv category includes more general AI safety papers. E.g. theory, position papers, etc.

*\*surfacing interesting papers \-\> summary\**

Researchers are busy, and having a quick, skimmable piece of information is useful. Maybe include a simple feature that’s just an AI generated summary (like Google lol) that summarizes the search results in a skimmable way.

*\*Papers \-\> tools for reading / engaging with the paper\**

When a user clicks on a paper, quickly generate an idea map for the paper (ideally at the speed of deepwiki). 

V1

- Idea map feature  
- Figure out how to collect information. For example:   
  - Users can write notes on the side that reference the paper. I think [Curius](https://curius.app/) has a way to highlight PDFs, should figure out how this works since references could be cool.

Extending the hypothesis tree

- One assumption I had was, if a paper returns as a match for a hypothesis, hypothesis the user writes under the paper should be \*linked\*. This isn’t always true, e.g. the paper might be about multiple subjects and the user might find another, unrelated claim interesting.

*\*Idea merging\**

The user might have related claims across different parts of their idea graph. Run an LLM periodically over the idea graph to merge related hypotheses and clean things up. Not sure if this is important, sort of low prio  
 

Getting papers / citations

- ArXiv API  
- Semantic Scholar API  
- NOTE: Apparently Google Scholar is hard to scrape, probably not worth dealing with rate limits and setting up third party packages like scholarly.

# Plan  v2

Have been mulling over the plans above and thinking for awhile, but finally created a GH repo lol. 

Created a Plan v2 tab which is a copy of v1 but with some changes and emphasis on certain features. Specifically: 

- Rather than showing a daily summary of relevant papers and sorting by the number of citations, I should sort in a diff based manner. Something like, “here’s what shifted in your hypothesis space today”  
- Some framing I dropped which I think I should put more emphasis on is new papers refuting / supporting claims. Surfacing papers which refute a hypothesis the user has seems way more useful than, “here are a couple of generally related papers”.  
- Not sure if the graph framing is strong, and it might not be super relevant. I don’t think it offers too much of an advantage over just a list of hypotheses.   
  - I think we could include some relations though. Like there could be a graph, but I don’t want to force it. E.g. if the user comments on a paper that was surfaced as part of a hypothesis, don’t immediately make it a child of the other hypothesis. Maybe just make it a dropdown or something.   
    - Rather than forcing the user to write comments, I think automatically having an LLM extract claims is super useful.  
- Should have some notes on hypothesis maintenance.   
- I also don’t only want to run LLM judges leaf hypothesis. Non leaf hypotheses are still relevant, just a parent hypothesis of another. Could be an issue of just having a lot of hypotheses though. 

I also think getting the idea map for a paper correct is super important. This is how we make it feasible for researchers to actually read papers\! I think this is an important part of the “keeping up” part of Vikrant’s wording. Lol, this plan is becoming more and more like Docent… woah\!

There’s one issue with the current system that’s slightly out of scope. Specifically, sometimes the user might write some hypothesis that has evidence in papers from previous days, but searching over prior papers is out of scope. I guess I’m a bit uncertain what ArXiv rate limits are and how much storage this would involve or else I would do this.

Here’s how I think hypothesis should work:

- The user writes a hypothesis which is a claim, e.g. “LLM as a judge evaluation is unreliable”   
- Search looks for papers which support or refute the claim and show them in the summary. It should also explain why the paper supports / refutes, as best as it can from the abstract.  
- The user can click on evidence and start an idea map generation \+ warrant chain search in the paper. They can upvote or downvote evidence here.

From within a paper, the user can write more claims, or deeper claims. E.g. “LLM as evaluation is unreliable because LLMs are overconfident and uncalibrated”. 

Stepping back for a second, does this system help users keep up with research in their field and stay informed? 

- Keep up, yes. I think this hypothesis search system is great.   
- Stay informed, I’m not sure. I guess, if the user is interested in SAEs, all papers might be about SAEs but not broadly about mech interp or AI safety.  
  - Here, I think it could be useful to have two layers. A topic layer, where the user is interested in general topics. And then a hypothesis layer, where the user sees relevant research for their interests.  
  - I guess, staying informed has the same problem of how does the user keep up with topics which are broad and have many matches and lots of papers which could be dense.   
    - This sort of presents a reranking problem, where the user has general topic interests, and we want to show papers sorted by relevance to their current interests.

Since staying generally informed is useful, I might try something like. The user can add different natural language filters to the daily papers: 

- Claims, which are things the user believes. The model will find evidence to support / refute these claims  
- Questions, which are things the user wants to understand. The model will find relevant papers and claims in the abstracts  
- Topics, which are general areas the user is interested in. The model will find relevant claims in the abstract.

---

**Plan v2**

Speccing out a bit how I’d like to build things: 

- Onboarding flow \-\> user interests  
- Filters \-\> surfacing interesting papers  
- Surfacing interesting papers \-\> summary  
- Papers \-\> tools for reading / engaging with the paper  
- Idea merging

\**Onboarding flow \-\> user interests*\*

Extract “filters” from the user onboarding. 

Filters can be of different types: claims, questions, topics

\**Filters \-\> surfacing interesting papers*\*

Search works like: 

- For each filter, run an LLM judge against the abstracts and have it pull the relevant stuff.   
- Within each filter, sort by relevance with tournament style reranking. 

I wonder if something like docent would be useful. Essentially having different llm judge output structures where the format is just: 

{  
“Filter name” :   
“Judge instructions”   
“Rerank”  
“Rerank instructions”  
“version”  
}

The version could be cool. Like, given the feedback a user has on the result relevancy, the prompt is automatically rewritten.

\**Surfacing interesting papers \-\> summary*\*

Idea map, efficiently get a summary from an arxiv paper

**\*\*working instructions\*\***

Next js app with shadcn, tanstack router. Do not manually write the package.json, use pnpm install with package names and have the dep resolver figure out package versions. For adding components, do not handwrite, use shadcn cli to install. Use tailwind, do not handwrite globals.css. 

The layout of the app is a shadcn sidebar with three pages: 

1. Filters, which just displays all the filters  
   - Initially it will be filled with the filters created by onboarding  
   - The user can create new filter types on this page too, e.g. other than question/claim/topic  
2. daily, which displays the daily search by default. The daily search runs all the filters against the day’s releases on arxiv  
- When the user clicks on a paper here, it opens onto a paper page. The paper page displays the core claims in the paper on the left and the paper pdf on the right. It jumps to the relevant page in the pdf when a core claim is clicked, or a warrant for that claim expanded.  
  - This is a reusable component, other pages will open into paper views  
3. Search  
- This page essentially just allows the user to change what filters are run and how far back to run things. Should not implement this page in v1. 
