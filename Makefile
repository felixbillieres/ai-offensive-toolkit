.PHONY: install install-all demo-evasion demo-fuzzer demo-privacy demo-cheatsheet lint clean help

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2}'

install: ## Install core dependencies
	pip install -r requirements.txt

install-all: install ## Install all dependencies including optional
	pip install adversarial-robustness-toolbox opacus fickling safetensors

# ── Demos ─────────────────────────────────────────────────

demo-evasion: ## Run FGSM/PGD attack demo on MNIST
	python -m evasion.fgsm_pgd --attack pgd --eps 0.3 --steps 10 --dataset mnist --visualize

demo-deepfool: ## Run DeepFool demo on MNIST
	python -m evasion.deepfool --batch-size 8

demo-cheatsheet: ## Print the torchattacks comparison table
	python -m evasion.torchattacks_cheatsheet

demo-fuzzer: ## List all prompt injection payloads
	python -m prompt_injection.fuzzer --list-payloads

demo-poison: ## Run label flipping demo on MNIST
	python -m data_poisoning.label_flipping --strategy targeted --source 7 --target 1 --rate 0.15 --epochs 3

demo-privacy: ## Run membership inference demo
	python -m privacy.membership_inference --method metric --threshold 0.9 --epochs 3

demo-trojan: ## Run trojan backdoor demo
	python -m data_poisoning.trojan_backdoor --source 7 --target 1 --poison-rate 0.1 --epochs 3

demo-stegano: ## Run tensor steganography demo
	python -m data_poisoning.pickle_exploit --mode stegano

demo-tampering: ## Run model tampering demo
	python -m app_system.model_tampering --mode inject --target-class 1

demo-all: demo-cheatsheet demo-evasion demo-poison demo-trojan demo-privacy demo-stegano ## Run all demos

# ── Development ───────────────────────────────────────────

lint: ## Check code with ruff
	ruff check .

format: ## Format code with ruff
	ruff format .

clean: ## Remove generated files
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	rm -rf data/ dist/ build/ *.egg-info
	rm -f *_results.json
