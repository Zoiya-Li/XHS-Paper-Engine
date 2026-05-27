# Build the pdffigures2 fat JAR reproducibly (used by scripts/build_pdffigures2_jar.sh).
# The JAR is the only artifact we need at runtime — this image is just the builder.
FROM eclipse-temurin:11-jdk-jammy

RUN apt-get update && apt-get install -y --no-install-recommends \
        curl git ca-certificates && \
    rm -rf /var/lib/apt/lists/*

# Pin sbt to the version pdffigures2 expects (project/build.properties = 1.7.1)
RUN curl -fL https://github.com/sbt/sbt/releases/download/v1.7.1/sbt-1.7.1.tgz \
      | tar -xz -C /opt
ENV PATH="/opt/sbt/bin:$PATH"

ARG PDFFIGURES2_REPO=https://github.com/allenai/pdffigures2.git
RUN git clone --depth 1 "$PDFFIGURES2_REPO" /pdffigures2
WORKDIR /pdffigures2

# build.sbt sets assemblyOutputPath := file("pdffigures2.jar")
RUN sbt -batch -error assembly && test -f /pdffigures2/pdffigures2.jar
