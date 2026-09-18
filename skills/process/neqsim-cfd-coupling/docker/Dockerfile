# OpenFOAM plus Python, so the cfd-coupling skill can drive a solver in-process.
#
# The upstream image ships OpenFOAM but no Python interpreter, so the skill
# cannot run inside it. This adds Python, gmsh and the skill itself.
#
#   docker build -t neqsim-cfd:latest docker/
#   docker run --rm -v "${PWD}:/work" -w /work neqsim-cfd:latest \
#       python3 -c "from cfd_coupling import detect_openfoam; print(detect_openfoam())"
FROM opencfd/openfoam-default:latest

USER root

RUN apt-get update \
    && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
        python3 \
        python3-pip \
        python3-venv \
    && rm -rf /var/lib/apt/lists/*

# PEP 668 marks the system interpreter as externally managed; this image is
# single-purpose, so installing into it directly is intended.
ENV PIP_BREAK_SYSTEM_PACKAGES=1
RUN python3 -m pip install --no-cache-dir gmsh numpy

COPY . /opt/cfd-coupling/
RUN python3 -m pip install --no-cache-dir /opt/cfd-coupling

# Lets detect_openfoam resolve without relying on a login shell.
ENV OPENFOAM_BASHRC=/usr/lib/openfoam/openfoam2512/etc/bashrc

WORKDIR /work
