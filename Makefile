VERSION=1.0
NAME=rust-makefile
EXEC=rust-exec
PREFIX=$(HOME)/.local

default: build_release

clean:
	@echo "Cleaning build dir"
	@rm -rf target/*
	@echo "Cleaning using cargo"
	@cargo clean
check:
	@echo "Checking $(NAME)"
	@cargo check
build_release:
	@echo "Building release: $(VERSION)"
	@set RUSTFLAGS=-C code-model=kernel -C codegen-units=1 && cargo build --release
	@strip target/release/$(EXEC)
build_debug:
	@echo "Building debug"
	@cargo build
run:
	@echo "Running debug"
	@cargo run
install_debug: build_debug
	@echo "Installing debug"
	@cp target/debug/$(EXEC) $(PREFIX)/bin
install: build_release
	@echo "Installing release: $(VERSION)"
	@cp target/release/$(EXEC) $(PREFIX)/bin