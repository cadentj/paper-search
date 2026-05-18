"""Deterministic mock paper provider for V1 daily searches."""

from datetime import datetime, timezone

MOCK_PAPERS = [
    {
        "arxiv_id": "2401.00001",
        "title": "Scaling Laws for Neural Language Models: A Comprehensive Analysis",
        "abstract": (
            "We study the scaling behavior of large language models across multiple axes: "
            "model size, dataset size, and compute budget. Our experiments reveal predictable "
            "power-law relationships that hold across several orders of magnitude. We find that "
            "larger models are significantly more sample-efficient, and that optimal allocation "
            "of a fixed compute budget involves training very large models on relatively modest "
            "amounts of data. These findings have implications for the efficient training of "
            "next-generation language models and suggest that current models are substantially "
            "undertrained relative to their optimal compute allocation."
        ),
        "authors": ["Sarah Chen", "Michael Zhang", "Emily Watson"],
        "categories": ["cs.CL", "cs.LG"],
        "published_at": "2024-01-15T00:00:00Z",
        "html_url": "https://arxiv.org/html/2401.00001",
        "landing_url": "https://arxiv.org/abs/2401.00001",
    },
    {
        "arxiv_id": "2401.00002",
        "title": "Mechanistic Interpretability of Transformer Attention Heads",
        "abstract": (
            "We present a systematic study of individual attention heads in transformer "
            "language models, identifying specific computational roles through causal "
            "interventions. Our analysis reveals that certain heads consistently perform "
            "induction, copying, or inhibition operations across diverse inputs. We develop "
            "automated tools for classifying head behavior and demonstrate that ablating "
            "heads with identified roles produces predictable downstream effects. These "
            "findings advance our understanding of how transformers implement algorithms "
            "and suggest pathways for more targeted model editing."
        ),
        "authors": ["David Kim", "Lisa Park", "Robert Johnson"],
        "categories": ["cs.LG", "cs.AI"],
        "published_at": "2024-01-16T00:00:00Z",
        "html_url": "https://arxiv.org/html/2401.00002",
        "landing_url": "https://arxiv.org/abs/2401.00002",
    },
    {
        "arxiv_id": "2401.00003",
        "title": "RLHF Alternatives: Direct Preference Optimization Without Reward Models",
        "abstract": (
            "Reinforcement learning from human feedback (RLHF) has become the standard "
            "approach for aligning language models with human preferences. However, RLHF "
            "requires training a separate reward model and using complex RL algorithms. "
            "We propose a simpler alternative that directly optimizes the policy using "
            "preference data without an explicit reward model. Our method, Direct Preference "
            "Optimization (DPO), is stable, performant, and computationally lightweight. "
            "Experiments show that DPO matches or exceeds RLHF performance across summarization "
            "and dialogue tasks while being significantly simpler to implement and tune."
        ),
        "authors": ["Alex Rivera", "Jennifer Lee", "Thomas Brown"],
        "categories": ["cs.CL", "cs.AI"],
        "published_at": "2024-01-17T00:00:00Z",
        "html_url": "https://arxiv.org/html/2401.00003",
        "landing_url": "https://arxiv.org/abs/2401.00003",
    },
    {
        "arxiv_id": "2401.00004",
        "title": "Sparse Autoencoders Reveal Interpretable Features in Language Models",
        "abstract": (
            "We train sparse autoencoders on the activations of large language models and "
            "discover that the learned features correspond to interpretable concepts. Each "
            "feature activates on semantically coherent sets of inputs, including topics, "
            "syntactic structures, and factual associations. We demonstrate that these features "
            "can be used for targeted model steering: amplifying or suppressing specific features "
            "predictably alters model behavior. Our approach provides a scalable method for "
            "understanding the internal representations of neural networks and opens new avenues "
            "for fine-grained model control without retraining."
        ),
        "authors": ["Maria Garcia", "James Wilson", "Anna Thompson"],
        "categories": ["cs.LG", "cs.AI"],
        "published_at": "2024-01-18T00:00:00Z",
        "html_url": "https://arxiv.org/html/2401.00004",
        "landing_url": "https://arxiv.org/abs/2401.00004",
    },
    {
        "arxiv_id": "2401.00005",
        "title": "Chain-of-Thought Prompting Elicits Reasoning in Large Language Models",
        "abstract": (
            "We explore how generating intermediate reasoning steps—chain-of-thought "
            "prompting—substantially improves the ability of large language models to perform "
            "complex reasoning. Experiments on arithmetic, commonsense, and symbolic reasoning "
            "benchmarks show that chain-of-thought prompting improves performance by up to 40%% "
            "on challenging tasks. We find that this capability emerges at sufficient model "
            "scale and does not require task-specific fine-tuning. Analysis of generated chains "
            "reveals that models produce coherent multi-step reasoning traces, though they "
            "occasionally exhibit systematic errors in longer chains."
        ),
        "authors": ["Kevin Wang", "Sophie Martinez", "Daniel Lee"],
        "categories": ["cs.CL", "cs.AI"],
        "published_at": "2024-01-19T00:00:00Z",
        "html_url": "https://arxiv.org/html/2401.00005",
        "landing_url": "https://arxiv.org/abs/2401.00005",
    },
    {
        "arxiv_id": "2401.00006",
        "title": "Constitutional AI: Harmlessness from AI Feedback",
        "abstract": (
            "We propose Constitutional AI (CAI), a method for training AI assistants that are "
            "helpful and harmless without relying on extensive human feedback on harmful outputs. "
            "The approach uses a set of principles (a constitution) to guide self-critique and "
            "revision during training. We show that CAI models can identify and refuse harmful "
            "requests while remaining helpful for benign queries. Compared to RLHF-trained "
            "models, CAI achieves similar helpfulness with improved harmlessness, and the "
            "approach is more transparent because the principles governing behavior are explicit "
            "and auditable."
        ),
        "authors": ["Rachel Adams", "Chris Taylor", "Natalie Nguyen"],
        "categories": ["cs.AI", "cs.CL"],
        "published_at": "2024-01-20T00:00:00Z",
        "html_url": "https://arxiv.org/html/2401.00006",
        "landing_url": "https://arxiv.org/abs/2401.00006",
    },
    {
        "arxiv_id": "2401.00007",
        "title": "Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks",
        "abstract": (
            "Large language models store factual knowledge in their parameters but struggle "
            "with knowledge-intensive tasks requiring precise, up-to-date information. We "
            "introduce a retrieval-augmented generation (RAG) framework that combines a "
            "pre-trained retriever with a sequence-to-sequence generator. The retriever fetches "
            "relevant documents from a large corpus, which the generator conditions on to "
            "produce outputs. RAG outperforms pure parametric models on open-domain question "
            "answering, fact verification, and knowledge-grounded dialogue, while providing "
            "interpretable evidence for its outputs through the retrieved passages."
        ),
        "authors": ["Paul Anderson", "Jessica White", "Mark Davis"],
        "categories": ["cs.CL", "cs.IR"],
        "published_at": "2024-01-21T00:00:00Z",
        "html_url": "https://arxiv.org/html/2401.00007",
        "landing_url": "https://arxiv.org/abs/2401.00007",
    },
    {
        "arxiv_id": "2401.00008",
        "title": "Emergent Abilities of Large Language Models: A Survey",
        "abstract": (
            "As language models scale, they exhibit emergent abilities—capabilities that are "
            "not present in smaller models but appear suddenly at larger scales. We survey "
            "documented emergent abilities across arithmetic, translation, reasoning, and "
            "code generation tasks. Our analysis finds that emergence is sensitive to how "
            "performance is measured: some abilities appear emergent under discrete metrics "
            "but show smooth improvement under continuous metrics. We discuss implications "
            "for AI safety, as emergent abilities may include unexpected and potentially "
            "dangerous capabilities that are difficult to predict from smaller-scale experiments."
        ),
        "authors": ["Laura Mitchell", "Andrew Clark", "Yuki Tanaka"],
        "categories": ["cs.CL", "cs.AI", "cs.LG"],
        "published_at": "2024-01-22T00:00:00Z",
        "html_url": "https://arxiv.org/html/2401.00008",
        "landing_url": "https://arxiv.org/abs/2401.00008",
    },
]


def get_daily_papers() -> list[dict]:
    """Return the deterministic mock paper batch for daily searches."""
    papers = []
    for p in MOCK_PAPERS:
        paper = dict(p)
        paper["published_at"] = datetime.fromisoformat(
            paper["published_at"].replace("Z", "+00:00")
        )
        papers.append(paper)
    return papers
