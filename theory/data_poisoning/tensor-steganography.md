# Tensor Steganography

> **In one sentence:** Hide arbitrary data (secrets, malware, a reverse-shell payload) inside the least significant bits of a model's weight tensors, where it rides along invisibly with no measurable effect on accuracy.

## What it is

Model weights are millions of `float32` numbers. Each `float32` has 23 mantissa bits, but the model's behavior only depends on the top few significant digits. The lowest mantissa bits are effectively noise. Tensor steganography rewrites those low bits to carry your data. The weights still work as weights, the model still predicts correctly, and hidden inside the "noise" is your payload.

```
Original weight: 0.12345678
Modified weight: 0.12345679   (1 bit changed, ~0% accuracy impact)
                         ^ hidden data bit
```

This is a **covert channel** and a **supply-chain** technique, not a learning attack. It pairs naturally with [pickle RCE](pickle-rce.md): the pickle payload runs the code, and the code reads the real payload out of the weights.

## The problem it exploits

`float32` (IEEE 754) is 1 sign bit, 8 exponent bits, 23 mantissa bits. Flipping the bottom mantissa bit changes the value by about 1.5e-8; flipping the top mantissa bit changes it by about 0.06. Model accuracy is robust to perturbations of order 1e-8 across individual weights (training itself is noisier than that), so the low bits are free real estate. Nobody diffs the 8th decimal digit of every weight, and even if they did, the changes look like ordinary floating-point noise.

## Intuition

Think of each weight as a long decimal number where only the first few digits matter for the model's decisions. The trailing digits are like the fine print nobody reads. Steganography writes a secret message into that fine print, one bit per weight (or a few). Read the model normally and you get a perfectly good model. Read the fine print in order and you get the hidden message. And there is a lot of fine print: a ResNet-50 has about 25 million parameters, so at 4 bytes each with 1 hidden bit per byte you can smuggle on the order of 12 MB.

## How it works

Encoding (the toolkit's `hide_data_in_tensor`, and the course's `encode_lsb`):

1. Flatten the target tensor and reinterpret each `float32` as its raw bytes / integer bits.
2. Turn the secret bytes into a bit stream. A robust format prefixes a length header (the course uses a 4-byte big-endian length via `struct.pack(">I", len)`) so the decoder knows when to stop.
3. Walk the tensor elements, and for each one clear the bottom `num_lsb` bits with a mask and OR in the next bits of the payload.
4. Reinterpret the modified bits back to `float32` and reshape to the original tensor shape.
5. Check capacity first: `len(payload) * 8` bits must fit in `num_elements * num_lsb`.

Decoding (`extract_data_from_tensor` / `decode_lsb`):

1. Flatten and reinterpret the tensor bits.
2. Read the low `num_lsb` bits from each element in order.
3. Reassemble bytes; if a length header was used, read it first, then read exactly that many payload bytes.

Tuning `num_lsb` (or `bit_depth`) trades capacity against stealth: 1 bit is maximally invisible, more bits store more data but perturb weights more and become detectable.

## Threat model and prerequisites

- **Capability:** write access to the model artifact (to embed) and the ability to get the victim to distribute or load it (to deliver). You are modifying the stored weights, not the training process.
- **Retrieval:** to *use* an offensive payload you need a way to read it back. Combined with [pickle RCE](pickle-rce.md), the `__reduce__` loader code decodes the LSBs and executes the hidden payload, all self-contained in one `.pth`.
- **No accuracy budget needed:** at 1 LSB the model's performance is preserved, which is what keeps the file looking legitimate.

## When to use it

- **Exfiltration / covert storage:** smuggle secrets out of, or into, an environment inside a file that looks like a normal model.
- **Payload staging:** hide a reverse shell or second-stage loader in the weights so the visible file is just a model, and only the pickle loader knows to extract and run it.
- **Watermarking / tracking:** embed an identifier to prove provenance or trace leaks (the same technique, benign intent).

## Step by step with the toolkit

Run the built-in steganography demo (embeds a flag, extracts it, and reports the weight change):

```
python -m data_poisoning.pickle_exploit --mode stegano
```

The demo creates a random `100x100` tensor, hides `b"FLAG{st3g4n0_1n_t3ns0rs}"` in the LSBs, extracts it back, confirms a byte-for-byte match, and prints the maximum and mean per-weight change (both tiny), demonstrating negligible impact.

Available flags (read `data_poisoning/pickle_exploit.py`):

- `--mode {create,scan,stegano}` (use `stegano` here)
- `--file` model path (used by `create` and `scan` modes)
- `--command` command embedded by `create` mode

The core functions to reuse in your own code:

- `hide_data_in_tensor(tensor, secret_bytes, bit_depth=1)` returns the modified tensor.
- `extract_data_from_tensor(tensor, num_bytes, bit_depth=1)` returns the recovered bytes.

For the full weaponized chain (payload hidden in weights, extracted and executed by a malicious `__reduce__`), see [pickle RCE](pickle-rce.md).

## Detection and defense

- **Statistical analysis of low-order bits:** truly trained weights have a characteristic LSB distribution; embedded data tends to look more uniform. Entropy tests on the mantissa LSBs can flag tampering.
- **Recompute or requantize weights:** re-saving through a lossy step (quantization, pruning, or converting to `safetensors` after a controlled transform) destroys hidden LSB payloads.
- **Hashing and signing:** any bit change alters the artifact hash, so signed models expose tampering regardless of where the change hides.
- **Provenance:** only accept models from trusted, verified sources.
- **Reminder:** steganography by itself is a channel, not code execution. The dangerous combo is steganography plus a pickle loader, so blocking [pickle RCE](pickle-rce.md) (with `weights_only=True` and `safetensors`) removes the automatic-execution leg.

## Explain it to a non-expert

Every weight in the model is like a very precise measurement, say 3.14159265 meters. The model only cares about the first few digits; the last digit or two are meaningless rounding. An attacker overwrites those last, ignored digits across millions of measurements, and if you read the overwritten digits in order they spell out a secret message or a piece of malware. The model still measures correctly, the file still looks like a normal model, but a hidden message is woven through the least important digits. It is like microscopic writing in the margin of every page of a book: the story reads fine, and only someone who knows to look in the margins finds the smuggled note.

## References

- Trail of Bits (2021), *Never a Dill Moment: Exploiting Machine Learning Pickle Files*
- IEEE 754 floating-point standard (float32 layout)
- See also: [overview](00-overview.md), [pickle RCE](pickle-rce.md)
