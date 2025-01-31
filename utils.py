import glob
import json
import os
import pathlib
import sys
import yaml


def get_config():
    # Trusted input.
    # https://github.com/yaml/pyyaml/wiki/PyYAML-yaml.load(input)-Deprecation
    try:
        with open("generator.yml") as f:
            return yaml.load(f, Loader=yaml.FullLoader)
    except FileNotFoundError as e:
        print_red("generator.yml not found?")
        raise e


def get_image_name():
    arch = os.environ["ARCH"]
    if arch == "powerpc":
        subarch = get_cbl_name()
        return {
            "ppc32": "uImage",
            "ppc64": "vmlinux",
            "ppc64le": "zImage.epapr"
        }[subarch]
    return {
        "arm": "zImage",
        "arm64": "Image.gz",
        "i386": "bzImage",
        "mips": "vmlinux",
        "riscv": "Image",
        "s390": "bzImage",
        "um": "linux",
        "x86_64": "bzImage",
    }[arch]


def get_cbl_name():
    arch = os.environ["ARCH"]
    full_config = os.environ["CONFIG"]
    base_config = full_config.split("+")[0]

    # Distribution configurations have a URL
    if "https://" in base_config:
        if "fedora" in base_config:
            fedora_to_cbl = {
                "aarch64": "arm64",
                "armv7hl": "arm32_v7",
                "i686": "x86",
                "ppc64le": "ppc64le",
                "s390x": "s390",
                "x86_64": "x86_64"
            }
            # The URL is https://.../kernel-<arch>-fedora.config
            fedora_arch = base_config.split("/")[-1].split("-")[1]
            return fedora_to_cbl[fedora_arch]
        if "openSUSE" in base_config:
            suse_to_cbl = {
                "arm64": "arm64",
                "armv7hl": "arm32_v7",
                "i386": "x86",
                "ppc64le": "ppc64le",
                "s390x": "s390",
                "x86_64": "x86_64"
            }
            # The URL is https://.../<arch>/default
            suse_arch = base_config.split("/")[-2]
            return suse_to_cbl[suse_arch]
        # Arch Linux is x86_64 only
        if "archlinux" in base_config:
            return "x86_64"

    # ChromeOS configurations have the architecture as the second to last
    # folder of the second config fragment path:
    # chromeos/config/chromeos/arm64/common.config
    # chromeos/config/chromeos/x86_64/common.config
    if "chromeos" in base_config:
        return full_config.split("+")[1].split("/")[-2]

    unique_defconfigs = {
        "multi_v5_defconfig": "arm32_v5",
        "aspeed_g5_defconfig": "arm32_v6",
        "multi_v7_defconfig": "arm32_v7",
        "malta_defconfig": "mipsel",
        "ppc44x_defconfig": "ppc32",
        "pseries_defconfig": "ppc64",
        "powernv_defconfig": "ppc64le",
    }
    if "CONFIG_CPU_BIG_ENDIAN=y" in full_config:
        if arch == "arm64":
            return "arm64be"
        if arch == "mips":
            return "mips"
    if base_config in unique_defconfigs:
        return unique_defconfigs[base_config]
    if "defconfig" in base_config:
        return "x86" if arch == "i386" else arch
    raise Exception("unknown CBL name")


def _read_builds():
    builds = "builds.json"
    if os.environ.get("MOCK"):
        builds = "mock.builds.json"
    try:
        with open(builds) as f:
            builds = json.load(f)
    except FileNotFoundError as e:
        print_red("Unable to find %s. Artifact not saved?" % (builds))
        raise e
    return builds


def get_requested_llvm_version():
    ver = os.environ["LLVM_VERSION"]
    ci_folder = pathlib.Path(__file__).resolve().parent
    with open(ci_folder.joinpath("LLVM_TOT_VERSION")) as f:
        llvm_tot_version = str(int(f.read())).strip()
    return "clang-" + ("nightly" if ver == llvm_tot_version else ver)


def show_builds():
    print_yellow("Available builds:")
    for build in _read_builds():
        print_yellow("\tARCH=%s LLVM_VERSION=%s CONFIG=%s" %
                     (build["target_arch"], build["toolchain"].split(
                         '-', 1)[1], "+".join(build["kconfig"])))


def get_build():
    arch = os.environ["ARCH"]
    configs = os.environ["CONFIG"].split("+")
    llvm_version = get_requested_llvm_version()
    for build in _read_builds():
        if build["target_arch"] == arch and \
           build["toolchain"] == llvm_version and \
           build["kconfig"] == configs:
            return build
    print_red("Unable to find build")
    show_builds()
    sys.exit(1)


def get_repo_ref(config, tree_name):
    for tree in config["trees"]:
        if tree["name"] == tree_name:
            return tree["git_repo"], tree["git_ref"]


def get_llvm_versions(config, tree_name):
    llvm_versions = set()
    repo, ref = get_repo_ref(config, tree_name)
    for build in config["builds"]:
        if build["git_repo"] == repo and build["git_ref"] == ref:
            llvm_versions.add(build["llvm_version"])
    return llvm_versions


def print_red(msg):
    print("\033[91m%s\033[0m" % msg, file=sys.stderr)
    sys.stderr.flush()


def print_yellow(msg):
    print("\033[93m%s\033[0m" % msg, file=sys.stdout)
    sys.stdout.flush()


def patch_series_flag(tree):
    ci_folder = pathlib.Path(__file__).resolve().parent
    patches_folder = pathlib.Path("patches").joinpath(tree)
    patch_files = glob.glob(
        ci_folder.joinpath(patches_folder).as_posix() + "/*.patch")
    return " --patch-series {}".format(
        patches_folder.as_posix()) if patch_files else ""
