package main

import (
	"context"
	"fmt"
	"io"
	"log/slog"
	"os"
)

type CustomHandler struct {
	level slog.Leveler
	w     io.Writer
}

func (h *CustomHandler) Enabled(_ context.Context, level slog.Level) bool {
	return level >= h.level.Level()
}

func (h *CustomHandler) Handle(_ context.Context, r slog.Record) error {
	level := r.Level.String()
	fmt.Fprintf(h.w, "%s[ostr] - %s\n", level, r.Message)
	return nil
}

func (h *CustomHandler) WithAttrs(attrs []slog.Attr) slog.Handler {
	return h
}

func (h *CustomHandler) WithGroup(name string) slog.Handler {
	return h
}

func initLogger(debug bool) {
	level := slog.LevelInfo
	if debug {
		level = slog.LevelDebug
	}

	handler := &CustomHandler{
		level: level,
		w:     os.Stdout,
	}

	logger := slog.New(handler)
	slog.SetDefault(logger)
}
