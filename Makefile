VERSION = 1.0
NAME = simeis
EXEC = $(NAME)
PREFIX = $(HOME)/.local


ifeq ($(OS),Windows_NT)
    IS_WINDOWS := 1
else
    IS_WINDOWS := 0
endif

default: all

clean:
    @echo "Nettoyage complet..."
    @rm -rf target/*
    @cargo clean
    @rm -f doc/manual.pdf


check:
    @echo "Verification du code ($(NAME))..."
    @cargo fmt --all -- --check
    @cargo clippy --all-targets --all-features


test:
    @echo "Lancement des tests..."
    @cargo test


release:
    @echo "Compilation release avec RUSTFLAGS..."
	ifeq ($(IS_WINDOWS), 1)
    	@set RUSTFLAGS=-C code-model=kernel -C codegen-units=1 && cargo build --release
    	@echo "Strip désactivé (Windows)"
    	@powershell -Command "Get-Item target/release/$(EXEC)* | Format-Table Name,Length"
	else
    	@RUSTFLAGS="-C code-model=kernel -C codegen-units=1" cargo build --release
    	@strip target/release/$(EXEC)
    	@ls -lh target/release/$(EXEC)
	endif


debug:
    @echo "Build debug..."
    @cargo build


run:
    @echo "Exécution (debug)..."
    @cargo run


manual:
    @echo "Compilation du manuel Typst..."
    @typst compile doc/manual.typ doc/manual.pdf


install_debug: debug
    @echo "Installation (debug)..."
    @mkdir -p $(PREFIX)/bin
    @cp target/debug/$(EXEC) $(PREFIX)/bin


install: release
    @echo "Installation (release)..."
    @mkdir -p $(PREFIX)/bin
    @cp target/release/$(EXEC) $(PREFIX)/bin

all: check test release manual