# PATE (Private Aggregation of Teacher Ensembles)

> **In one sentence:** Split the private data among many "teacher" models, have them vote on unlabeled public data, add noise to the vote counts, and train a "student" model only on those noisy votes, so the deployed student never touches private data and cannot leak it.

## What it is

PATE (Papernot et al., 2017) is a differentially private training method that, unlike [dp-sgd.md](dp-sgd.md), does not add noise inside one model's training. Instead it breaks the link between the deployed model and the sensitive data at the architectural level. The private data trains a committee of teachers; the teachers label public data through a noisy vote; a student learns from those labels and is the only model you deploy. The student never sees a private record.

```
DP-SGD : private data  ->  noisy training      ->  model
PATE   : private data  ->  teachers -> noisy votes -> public labels -> student
                                                          (student never sees private data)
```

## The attack it stops

Like DP-SGD, PATE protects the **training data** and provably limits:

- **Membership inference** ([../privacy/membership-inference.md](../privacy/membership-inference.md)).
- **Model inversion** ([../privacy/model-inversion.md](../privacy/model-inversion.md)).
- **Memorization** of individual private records.

It does **not** address evasion ([adversarial-training.md](adversarial-training.md)) or LLM jailbreaks ([llm-guardrails.md](llm-guardrails.md)).

## Intuition

Two ideas do the work.

**Information bottleneck.** Megabytes of private data get compressed into a few thousand noisy labels of a few kilobytes. In the course example, about 48,000 MNIST images (roughly 150 MB) become 5,000 labels (about 2.5 KB), a compression above 60,000 to 1. No attack can reconstruct megabytes of private data from kilobytes of noisy labels; it is an information-theoretic limit, not just a practical one.

**Consensus dilutes memorization.** Suppose one teacher was trained on the partition containing Alice. That teacher's vote may be biased by having memorized Alice. But the other teachers never saw Alice, so they vote from generalization. One biased vote out of, say, 250 is a weak membership signal, and the added noise obscures whether the majority came from memorization or genuine generalization.

## How it works

Two phases (implemented in the toolkit's `train_pate`).

### Phase 1: teachers on disjoint partitions

Split the sensitive data into `N` **disjoint** subsets and train one teacher per subset. No teacher sees more than `1/N` of the data, so no single teacher can, on its own, reveal one individual's pattern. In the original paper `N` is large (for example 250 teachers on MNIST, about 192 samples each), which yields strong consensus.

### Phase 2: noisy aggregation and student training

For each unlabeled **public** sample `x`:

1. Every teacher votes for a class, forming a vote histogram `n_j(x)`.
2. Add noise to each class count and take the argmax:

```
y_hat = argmax_j [ n_j(x) + noise ]
```

The toolkit adds Laplace noise (`noise_scale`), matching the classic PATE mechanism; the label sensitivity is 2 because moving one training sample can shift at most one vote, changing two histogram entries by one.

3. The student trains on `(x, y_hat)`. The toolkit keeps only samples where the teachers reached strong consensus (60 percent agreement), since those noisy labels are the most reliable.

Once trained, the student can be queried without limit at no further privacy cost, because it never accesses private data again.

### The privacy budget

Each teacher query on a public sample spends budget. Naive composition is unusable (5,000 queries times a per-query `epsilon` of 0.10 gives 500). Advanced composition and, in practice, the moments accountant give a far tighter total: the course example reaches `epsilon` about 8.81 for 5,000 queries at `noise_scale=20`, roughly 57 times tighter than naive.

Three data pools are mandatory and must stay separate:

```
Private data  -> trains the teachers only
Public data   -> labeled by the noisy ensemble -> trains the student
Holdout       -> final evaluation only, never touched
```

## What it costs

- **You must train many models.** `N` teachers plus a student. That is more total compute than one DP-SGD run, though each teacher is small.
- **You need unlabeled public data** from a similar distribution. Without it, PATE does not apply. This is its biggest practical constraint.
- **Query budget limits student data.** Each label spent costs privacy, so the student trains on a limited number of labels, capping its accuracy.
- **Consensus loss.** Keeping only high-consensus samples discards the hard cases, which can bias the student.
- **Accuracy/privacy tradeoff** still applies, though PATE often reaches better accuracy than DP-SGD at a comparable `epsilon` when strong consensus exists.

## When to use it

- You have sensitive labeled data **and** access to unlabeled public data from a similar domain.
- You want the deployed model to have a clean architectural separation from the private data (easy to argue to auditors and regulators).
- Your task has strong teacher agreement (for example clear classification), so the noisy vote still yields correct labels.

If you have no public data, use [dp-sgd.md](dp-sgd.md) instead, which needs only the private set.

## Step by step with the toolkit

The script is `privacy/dp_defenses.py`. The `pate` method trains the teacher ensemble, runs the noisy vote on the test set as stand-in public data, and trains a student.

```bash
python -m privacy.dp_defenses --method pate --n-teachers 10 --epochs 10
```

Flags relevant to PATE (from the `argparse` block):

- `--method pate`  select PATE.
- `--n-teachers`  number of teachers to train (default 10). More teachers = stronger consensus and privacy, but each teacher sees less data.
- `--epochs`  student training epochs (default 10).

The run prints each teacher as it trains, the consensus count (how many public samples the teachers agreed on strongly enough to use), the student's training loss, and the final student test accuracy. Increase `--n-teachers` and watch consensus and privacy strengthen while each teacher's individual accuracy falls.

Verify the privacy payoff by attacking the student with membership inference and comparing to a normally trained model:

```bash
python -m privacy.membership_inference --help
```

See [../privacy/membership-inference.md](../privacy/membership-inference.md).

## Limitations and bypasses

- **No public data, no PATE.** The whole method depends on having unlabeled public data; that is the number one blocker.
- **Weak consensus leaks or fails.** If teachers disagree, the noise flips labels (bad student accuracy) or, if you cut noise to fix that, privacy weakens. Hard-to-classify tasks fit PATE poorly.
- **Too few teachers.** With a small `N`, one teacher carries too much weight, the membership signal is not diluted enough, and the guarantee weakens.
- **Distribution shift.** If public data differs from private data, teacher votes are unreliable and the student is both less accurate and less private in practice.
- **Bad accounting.** As with all DP, using naive composition or a wrong accountant misreports the real `epsilon`.
- **Nothing against evasion or jailbreaks.** It is purely a data-privacy defense.

## Explain it to a non-expert

Imagine you want expert advice built from many private patient files without ever exposing a single file. You give each of 250 doctors a small, separate slice of the records and let each learn from their slice alone. Then, for a set of anonymous public cases, you ask all 250 doctors to vote on the diagnosis, jot down the vote tallies, and smudge those tallies with a bit of random noise before taking the majority. A trainee then studies only these smudged majority answers on public cases. The trainee becomes a good diagnostician yet has never seen a single private file, and because each doctor saw only a sliver and the votes were noised, no one can tell whether any particular patient's record was ever used.

## References

- Papernot et al., 2017, "Semi-supervised Knowledge Transfer for Deep Learning from Private Training Data" (PATE).
- Papernot et al., 2018, "Scalable Private Learning with PATE."
- Course material: `11-ai-privacy/04_Private_Aggregation_Of_Teacher/`.
- Toolkit script: `privacy/dp_defenses.py`.
- Related pages: [dp-sgd.md](dp-sgd.md), [../privacy/membership-inference.md](../privacy/membership-inference.md), [../privacy/model-inversion.md](../privacy/model-inversion.md).
