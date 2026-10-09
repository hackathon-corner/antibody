# syntax=docker/dockerfile:1
# Builds the pinned Juice Shop target, optionally with one candidate patch applied.
# Adapted from the upstream Dockerfile at the pinned commit (MIT, OWASP Juice Shop).
# Build via scripts/target.py, which passes every pin from config/targets/juice-shop.json.
# Build context: a directory holding build-fixes/*.patch and candidate.patch (empty file = baseline).

ARG GIT_IMAGE
ARG BUILD_IMAGE
ARG RUNTIME_IMAGE

FROM ${GIT_IMAGE} AS source
ARG SOURCE_REPO
ARG SOURCE_COMMIT
WORKDIR /src
RUN git init -q . \
 && git fetch -q --depth 1 "${SOURCE_REPO}" "${SOURCE_COMMIT}" \
 && git checkout -q FETCH_HEAD \
 && test "$(git rev-parse HEAD)" = "${SOURCE_COMMIT}"
# Host-owned build fixes first (see infra/containers/README.md), then the candidate.
COPY build-fixes/ /build-fixes/
RUN for f in /build-fixes/*.patch; do git apply --whitespace=nowarn "$f"; done
COPY candidate.patch /candidate.patch
RUN if [ -s /candidate.patch ]; then git apply --check /candidate.patch && git apply /candidate.patch; fi
# Mirror upstream .dockerignore.
RUN rm -rf .git monitoring screenshots test vagrant logs Dockerfile .npmrc

FROM ${BUILD_IMAGE} AS installer
COPY --from=source /src /juice-shop
WORKDIR /juice-shop
RUN npm install -g typescript@^6.0.3
RUN npm install --omit=dev
# Upstream postinstall swallows server compile errors; a candidate that does not compile must fail here.
RUN npm run build:server
RUN npm dedupe --omit=dev
RUN rm -rf frontend/node_modules frontend/.angular frontend/src/assets
RUN mkdir logs
RUN chown -R 65532 logs
RUN chgrp -R 0 ftp/ frontend/dist/ logs/ data/ i18n/
RUN chmod -R g=u ftp/ frontend/dist/ logs/ data/ i18n/
RUN rm ftp/legal.md || true
RUN rm i18n/*.json || true

FROM ${RUNTIME_IMAGE}
ARG SOURCE_COMMIT
ARG CANDIDATE_HASH
LABEL org.opencontainers.image.title="Antibody target: OWASP Juice Shop" \
      org.opencontainers.image.licenses="MIT" \
      org.opencontainers.image.source="https://github.com/juice-shop/juice-shop" \
      org.opencontainers.image.revision="${SOURCE_COMMIT}" \
      antibody.candidate_hash="${CANDIDATE_HASH}"
WORKDIR /juice-shop
COPY --from=installer --chown=65532:0 /juice-shop .
USER 65532
EXPOSE 3000
CMD ["/juice-shop/build/app.js"]
