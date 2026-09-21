# Makefile — one target per corpus program: compile, analyse, extract, render.
#
# NOTE: `make` is not installed on the development host (no sudo, no apt), so this file is
# UNTESTED there and build.sh is the artefact of record. They do the same thing; build.sh is
# what produced every figure currently in render/figures/.
#
#   make M01     compile + analyse (both configs) + extract + render
#   make clean   remove build products; never touches ../stava

JAVA_HOME_STAVA ?= /home/harshil/jvm/jdk8u502-b07
JDK_LABEL       ?= Temurin 8u502-b07
HEAP            ?= 3g

.PHONY: all M01 E01 E09 E10 E11 reasons clean

all: M01

M01:
	JAVA_HOME_STAVA=$(JAVA_HOME_STAVA) JDK_LABEL="$(JDK_LABEL)" HEAP=$(HEAP) \
	./build.sh M01_mixed M01 "M01 Box Item Node" "<M01: void main(java.lang.String[])>"

E01:
	JAVA_HOME_STAVA=$(JAVA_HOME_STAVA) JDK_LABEL="$(JDK_LABEL)" HEAP=$(HEAP) \
	./build.sh E01_local_containment E01 "E01 Box Item" "<E01: void main(java.lang.String[])>"

# Phase 11: the two ground-truth programs for the escape-reason multiplicity axis.
E09:
	JAVA_HOME_STAVA=$(JAVA_HOME_STAVA) JDK_LABEL="$(JDK_LABEL)" HEAP=$(HEAP) \
	./build.sh E09_multi_reason E09 "E09 Item" "<E09: Item make()>"

E10:
	JAVA_HOME_STAVA=$(JAVA_HOME_STAVA) JDK_LABEL="$(JDK_LABEL)" HEAP=$(HEAP) \
	./build.sh E10_single_reason_each E10 "E10 Item Oops"

E11:
	JAVA_HOME_STAVA=$(JAVA_HOME_STAVA) JDK_LABEL="$(JDK_LABEL)" HEAP=$(HEAP) \
	./build.sh E11_three_surviving_reasons E11 "E11 Oops" "<E11: void make()>"

reasons: E09 E10 E11

clean:
	rm -rf build/out build/logs build/E01 build/M01 build/E09 build/E10 build/E11 build/tools
	@echo "left alone: build/stava-src-*, build/classes-* (slow to rebuild), ../stava"
