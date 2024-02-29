import os
import shutil
import tempfile
from pathlib import Path

from ayon_core.lib import PreLaunchHook
from ayon_openrv import OPENRV_ROOT_DIR
from ayon_core.lib.execute import run_subprocess
from ayon_core.pipeline.colorspace import get_imageio_config
from ayon_core.pipeline.template_data import get_template_data_with_names


class PreSetupOpenRV(PreLaunchHook):
    """Pre-hook for openrv"""
    app_groups = ["openrv"]

    def execute(self):
        executable = self.application.find_executable()

        # We use the `rvpkg` executable next to the `rv` executable to
        # install and opt-in to the Ayon plug-in packages
        rvpkg = Path(os.path.dirname(str(executable))) / "rvpkg"
        packages_src_folder = Path(OPENRV_ROOT_DIR) / "startup" / "pkgs_source"

        # TODO: Are we sure we want to deploy the addons into a temporary
        #   RV_SUPPORT_PATH on each launch. This would create redundant temp
        #   files that remain on disk but it does allow us to ensure RV is
        #   now running with the correct version of the RV packages of this
        #   current running Ayon version
        op_support_path = Path(tempfile.mkdtemp(
            prefix="openpype_rv_support_path_"
        ))

        # Write the Ayon RV package zips directly to the support path
        # Packages/ folder then we don't need to `rvpkg -add` them afterwards
        packages_dest_folder = op_support_path / "Packages"
        packages_dest_folder.mkdir(exist_ok=True)
        packages = ["comments", "ayon_menus", "ayon_scripteditor"]
        for package_name in packages:
            package_src = packages_src_folder / package_name
            package_dest = packages_dest_folder / "{}.zip".format(package_name)

            self.log.debug(f"Writing: {package_dest}")
            shutil.make_archive(str(package_dest), "zip", str(package_src))

        # Install and opt-in the Ayon RV packages
        install_args = [rvpkg, "-only", op_support_path, "-install", "-force"]
        install_args.extend(packages)
        optin_args = [rvpkg, "-only", op_support_path, "-optin", "-force"]
        optin_args.extend(packages)
        run_subprocess(install_args, logger=self.log)
        run_subprocess(optin_args, logger=self.log)

        self.log.debug(f"Adding RV_SUPPORT_PATH: {op_support_path}")
        support_path = self.launch_context.env.get("RV_SUPPORT_PATH")
        if support_path:
            support_path = os.pathsep.join([support_path,
                                            str(op_support_path)])
        else:
            support_path = str(op_support_path)
        self.log.debug(f"Setting RV_SUPPORT_PATH: {support_path}")
        self.launch_context.env["RV_SUPPORT_PATH"] = support_path

        # set $OCIO
        template_data = get_template_data_with_names(
            project_name=self.data["project_name"],
            asset_name=self.data["folder_path"],
            task_name=self.data["task_name"],
            host_name=self.host_name,
            settings=self.data["project_settings"]
        )

        config_data = get_imageio_config(
            project_name=self.data["project_name"],
            host_name=self.host_name,
            project_settings=self.data["project_settings"],
            anatomy_data=template_data,
            anatomy=self.data["anatomy"],
            env=self.launch_context.env,
        )

        if config_data:
            ocio_path = config_data["path"]

            if self.host_name in ["nuke", "hiero"]:
                ocio_path = ocio_path.replace("\\", "/")

            self.log.info(
                f"Setting OCIO environment to config path: {ocio_path}")

            self.launch_context.env["OCIO"] = ocio_path
        else:
            self.log.debug("OCIO not set or enabled")
