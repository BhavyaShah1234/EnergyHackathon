Let's start from absolute zero and build up to the full picture. No jargon until I've explained it in plain English first.

---

## The World That Created This Problem

Imagine you're a company like Google, Microsoft, or OpenAI. You're building the most powerful AI systems in the world — ChatGPT, Gemini, Copilot. To train and run these AI models, you need warehouses full of computers called **data centers**. These aren't normal computers. A single AI training run can consume as much electricity as a small town.

So your #1 constraint isn't money. It isn't land. It isn't engineers. **It's electricity.** You need massive, reliable, uninterrupted power — delivered the moment you flip the switch, not 5 years from now.

Here's the problem: **the electricity grid wasn't built for this.**

---

## Analogy: The City Water System

Think of the public electricity grid like a city's water supply system. It works fine for homes and small businesses. But now imagine a million new residents suddenly moved to your city and all wanted to fill Olympic swimming pools every day. The pipes, pumps, and reservoirs weren't designed for that. You'd have to wait years while the city built new infrastructure.

That's exactly what's happening with AI data centers and the power grid. Grid interconnection timelines have stretched to 3–7 years in many markets — far longer than the 18–24 months it actually takes to construct a data center.

So what do the smart data center developers do? They stop waiting for the city's water system. They **dig their own well.**

That "digging your own well" is called **Behind The Meter (BTM) power** — specifically, building a natural gas power plant right on your property so you never need the public grid at all.

---

## Why Natural Gas Specifically?

You could use solar. You could use wind. But AI data centers run 24 hours a day, 7 days a week. The sun sets. The wind stops. Natural gas burns on demand, any time, any weather. Texas gas solutions company VoltaGrid and Energy Transfer announced they will supply Oracle with 2.3 GW of off-grid fossil gas power for its data centers — fully self-powered, no public grid involved.

Texas and the Southwest are the perfect location for this because they have:
- Abundant cheap natural gas (Waha Hub — West Texas)
- Massive available land
- Business-friendly permitting
- No state income tax

---

## The Master Problem: Three Locks, One Key

So the plan is clear: find land in Texas or the Southwest, pipe in natural gas, build a gas power plant on-site, and run your data center. Simple, right?

Not quite. Every site you consider has **three separate problems that all have to be solved simultaneously** — like a combination lock with three dials. Every dial has to be right or the whole thing fails.

Think of it like buying a house:
- The house has to be in a good neighborhood (land)
- The plumbing has to work reliably (gas supply)
- The mortgage payments have to be affordable (power economics)

If any one of those fails, you don't buy the house. But right now, companies evaluate these three things **in separate teams, in separate spreadsheets, weeks apart.** By the time they realize dial #3 is wrong, they've already spent months on dials #1 and #2.

**The master problem:** Build an AI platform that evaluates all three dials at the same time, for thousands of candidate sites, and tells you which sites are genuinely viable — ranked by overall quality.

---

## Sub-Problem A: Finding the Right Land

### What the problem is

Imagine you're a real estate agent, but instead of finding a 3-bedroom house, you need to find a plot of land that is:
- At least 50 to 500+ acres (roughly 50–500 football fields)
- Already zoned to allow heavy industrial use (you can't build a gas power plant in a residential neighborhood)
- Close to underground fiber optic cables (your data center needs to connect to the internet)
- Near a water source (your computers generate enormous heat and need cooling water)
- Not in a flood zone
- Available to buy or lease at a reasonable price
- With no legal complications — no environmental protections, no disputed ownership, no utility easements cutting through it

Now do this for thousands of candidate plots across Texas, Arizona, and New Mexico. Manually. That's what developers currently do — and it takes months.

### The analogy

It's like trying to find the perfect campsite in a national park, but you have 10,000 campsites to evaluate, each with different rules, different terrain, different water access, and different fee structures — and you're doing it by reading 10,000 individual handwritten forms.

### What the AI solution does

Instead of reading forms manually, the AI ingests public government databases — the Texas General Land Office (which tracks every parcel of land in Texas), the HIFLD database (which maps every fiber cable underground), the USGS hydrography dataset (which maps every river, lake, and water body) — and automatically scores every parcel on every dimension simultaneously.

The really clever part is using **natural language AI** (like Claude) to read the actual legal deed documents for each parcel. These deeds are written in dense legal language. The AI extracts the key information: Is there an easement? Is there a lease restriction? Is the title clear? What was negotiated in the last sale? This would take a lawyer weeks per parcel. The AI does it in seconds.

**Output:** A ranked list of parcels. Site #1 is best for a BTM data center. Site #847 is terrible. Here's exactly why.

---

## Sub-Problem B: Can You Actually Get Reliable Gas There?

### What the problem is

You've found perfect land. Now you need to pipe natural gas to it to fuel your power plant. Natural gas travels through underground pipelines — some are massive interstate pipelines (like highways), others are smaller local distribution pipes (like city streets).

Here's the scary part: **some of those pipes are old. Very old.** Some are made of cast iron or bare steel, installed in the 1950s. They corrode. They crack. They leak. And when a gas pipeline fails, your power plant loses fuel and your data center goes dark.

This became horrifyingly real during **Winter Storm Uri in February 2021.** A historic freeze hit Texas. Gas wells froze. Pipelines froze. Gas supply dropped. Power plants lost fuel. The grid collapsed. Millions of Texans lost power for days. People died.

A data center cannot tolerate this. A single hour of downtime can cost millions of dollars and violates service agreements with customers.

### The analogy

Imagine you're opening a restaurant and your entire menu depends on one specific supplier delivering fresh ingredients every morning. Before you sign the lease, you'd want to know: How reliable is this supplier? Have they ever missed a delivery? Do they have a backup? What happens in a snowstorm?

Now imagine you can't easily call the supplier and ask. Instead, you have to dig through 50 years of government complaint records to figure out how often this supply chain has failed, where it failed, and what caused it.

That's exactly what this sub-problem asks you to build — an automated system that reads 50+ years of government pipeline incident records and predicts how likely any given gas supply route is to fail.

### What the AI solution does

The U.S. government's Pipeline and Hazardous Materials Safety Administration (PHMSA) maintains a database of every reported gas pipeline incident since 1970 — the cause, the location, the pipe material, the age of the pipe, the severity.

The AI uses **survival analysis** — a statistical technique originally developed for medical research to predict how long patients survive after a diagnosis — and applies it to pipelines instead. "How long does a cast-iron pipe installed in 1962 survive before its first failure?" The model answers this for every pipeline segment near your candidate sites.

It also builds a **network map** of pipeline redundancy. If the main pipeline to your site fails, is there a backup route? How many supply points feed your area? The more redundant the network, the lower the risk score.

**Output:** A "gas reliability index" for each candidate site. Red zones mean you'd need to invest in backup fuel storage or redundant pipeline connections. Green zones mean the gas supply is highly reliable.

---

## Sub-Problem C: Is It Actually Cheaper to Make Your Own Power?

### What the problem is

You have great land. You have reliable gas supply. Now the final question: **is building and running your own gas power plant actually cheaper than just buying electricity from the grid when you need it?**

This sounds obvious — surely making your own power is always cheaper than buying it? Not always. Here's why:

The price of grid electricity (called the **LMP — Locational Marginal Price**) fluctuates constantly. At 3am on a calm spring night in Texas, when wind turbines are spinning and nobody needs much power, electricity can cost almost nothing — even go negative (the grid pays you to take electricity). At 4pm on a record-hot August afternoon when everyone's air conditioning is blasting, electricity can spike to hundreds of times the normal price.

Meanwhile, your cost to generate your own power depends on the price of natural gas — which also fluctuates. If gas is cheap and grid electricity is expensive, make your own. If gas is expensive and grid electricity is cheap, buy from the grid.

The spread between "cost to make" and "cost to buy" — called the **BTM spread** — determines whether your private power plant is profitable or wasteful at any given moment.

### The analogy

You commute to work every day. You have two options:
- Drive your own car (pay for gas + wear-and-tear)
- Take an Uber (pay surge pricing when it's busy, cheap rate when it's not)

Some days, surge pricing is so high you'd be insane not to drive. Other days, parking is $30 and Uber is $8, so you leave the car home. The smart decision changes every day based on current prices.

Now imagine you're making this decision for a 500-megawatt data center, every 15 minutes, at thousands of different possible locations across Texas and the Western US, for the next 20 years. That's what Sub-problem C is.

### What the AI solution does

The AI ingests real-time and historical data from ERCOT (Texas's electricity market) and EIA (gas prices at Waha Hub in West Texas and Henry Hub in Louisiana) — and trains a forecasting model that predicts the BTM spread 6 to 72 hours into the future.

The clever addition is a **regime classifier** — an AI that recognizes which "mode" the market is currently in:
- **Scarcity mode:** Everybody needs power, LMP is spiking → generate your own, never import.
- **Oversupply mode:** Wind is dumping cheap power, LMP is near zero → import from grid, shut the turbine down.
- **High-wind curtailment mode:** West Texas wind is producing so much power that prices crash → great time to charge batteries from the grid.

Each regime requires a completely different operating strategy. The AI identifies which regime you're in and tells the data center operator what to do.

**Output:** A 72-hour forecast of whether self-generation is profitable at each candidate site, with confidence intervals — and a long-run estimate of which sites have the most durable positive spread over the next 10–20 years.

---

## The Full Stack: How All Three Connect

Now here's where it gets elegant. The three sub-problems aren't just run separately — they feed into each other in sequence, like a funnel:

**Step 1 — Sub-problem A produces the shortlist.** Out of 10,000 candidate parcels, maybe 200 pass the land and infrastructure filter. These are your viable sites.

**Step 2 — Sub-problem B filters the shortlist.** Of those 200, maybe 60 have acceptable gas supply reliability. The other 140 would require millions of dollars in pipeline reinforcement or backup fuel storage — making them economically unattractive.

**Step 3 — Sub-problem C ranks the survivors.** Of those 60, the spread forecasting model computes the long-run economics of each site. The top 5 are presented to the developer with a full financial picture.

**Final output:** A scorecard for each surviving site, with three dimensions — land quality, gas reliability, power economics — combined into one composite score. The developer can twist sliders ("what if gas prices rise 50%?", "what if LMP falls by 30%?") and watch the rankings shift in real time.

Here's the entire journey from raw data to actionable decision:---

## The Whole Story in One Paragraph

AI companies need data centers. Data centers need enormous amounts of electricity immediately. The public grid can't provide it fast enough — you'd wait 7 years. So the solution is to build a private natural gas power plant right on the data center property (BTM). But to do that, you need to find land that is the right size, legally clean, and connected to fiber and water — while also making sure the gas pipelines feeding that land are reliable enough to never fail — while also making sure that generating your own gas power is actually cheaper than just buying electricity from the grid at that location. These three things have never been evaluated together automatically. The platform this hackathon asks you to build does exactly that: ingest public government data, run AI models on all three dimensions in parallel, and hand a developer a ranked shortlist of sites with full risk and cost estimates — in minutes instead of months.