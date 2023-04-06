import json
import os
import shutil
import time

from maya import cmds, mel


# Asset Library Batch Processor
# Requirements:
#     - Work with any folder structure
#     - For every mesh:
#           - Snap mesh dimensions to the nearest grid point
#           - Adjust all pivots to the specified space in the FBX (Center, bottom-left, bottom center, ...)
#           - Exclude, but still copy, files from processing: FBX only copy vs. all copy
#           - Log file: Keeps track of stuff that's been done (e.g. scale by extreme amount.)
#     - Script has thought-out visuals during the process
#     - Preset file
#     - Additional features


class BatchProcessor(object):
    __OPTION_VAR_NAME = "Batch_Processor_Prefs"
    __PREF_FILE_NAME = "AL_BatchProcessor_Prefs.json"

    def __init__(self):
        """
        Initialises a BatchProcessor object and runs the script.
        """

        # -- Check whether already open -- #

        if cmds.window("AssetLibraryBatchProcessor", ex=True):
            cmds.showWindow("AssetLibraryBatchProcessor")
            cmds.setFocus("AssetLibraryBatchProcessor")
            return

        if cmds.window("ALBP_Progress", ex=True):
            cmds.showWindow("ALBP_Progress")
            cmds.setFocus("ALBP_Progress")
            return

        # -- Setup variables -- #

        self._root = cmds.workspace(q=True, rd=True)[:-1]   # The source folder.
        self._dest = ""                                     # The destination folder.

        # All variables to do with exporting and processing settings
        self.fbx_only = True                            # True if only fbx files get copied over.
        self.combine_meshes = True                      # True if wanting to combine meshes within one fbx file.
        self.own_fbx = False                            # Each mesh will get their own fbx if true. (Combine is False)
        self.pivot = True                               # True if pivot has to be changed.
        self.pivot_placement = [1, 1, 1]                # Pivot placement per axis: 0 = min, 1 = middle, 2 = max.
        self.scaling = True                             # True if scaling is wanted for the objects.
        self.scale = [50.0, 50.0, 50.0, 50.0]           # The text fields containing the scaling to snap objects to.
        self.allow_stretching = True                    # True if models are allowed to be stretched.
        self.main_axis = 0                              # The main axis in case stretching is not allowed.
        self.dest_changed = False                       # Whether the destination has changed since starting the script.

        self.__load_prefs()

        # The log file.
        self._log_file = ""

        # Window variables.
        self._window = "AssetLibraryBatchProcessor"     # The window.
        self.__files_layout = ""                        # The layout containing the file panel.
        self.__files_scroll = ""                        # The scroll layout containing the tree view.
        self.__folder_structure = None                  # The folder structure shown in the UI.

        self.__progress_window = "ALBP_Progress"        # The window shown when processing is in progress.

        # -- Create the window and run -- #

        self.__create_window()
        self.run()

    # ################################################################### #
    # ################## Helper Functions and Classes ################### #
    def __load_prefs(self):
        """
        Loads saved preferences into the Batch Processor if any are present.
        """

        if cmds.optionVar(ex=self.__OPTION_VAR_NAME):
            path = cmds.optionVar(q=self.__OPTION_VAR_NAME)

            # if found, then load in the preferences saved.
            if os.path.exists(path):
                with open(path, "r") as f:
                    preset = json.loads(f.readline())

                self._dest = preset["dest"]
                self.fbx_only = preset["fbx_only"]
                self.combine_meshes = preset["combine"]
                self.own_fbx = preset["own_fbx"]
                self.pivot = preset["pivot"]
                self.pivot_placement = preset["pivot_placement"]
                self.scaling = preset["scaling"]
                self.scale = preset["scale"]
                self.allow_stretching = preset["stretching"]
                self.main_axis = preset["main_axis"]

    def __save_prefs(self):
        """
        Saves the current Batch Processor settings to a JSON file in the user's preference directory.
        """

        prefs = {
                    "dest": self._dest,
                    "fbx_only": self.fbx_only,
                    "combine": self.combine_meshes,
                    "own_fbx": self.own_fbx,
                    "pivot": self.pivot,
                    "pivot_placement": self.pivot_placement,
                    "scaling": self.scaling,
                    "scale": self.scale,
                    "stretching": self.allow_stretching,
                    "main_axis": self.main_axis
                 }

        path = cmds.internalVar(upd=True)
        file = os.path.join(path, self.__PREF_FILE_NAME)
        with open(file, "w") as f:
            f.write(json.dumps(prefs))

        # Create a variable for the file location to find it back upon restart.
        cmds.optionVar(sv=(self.__OPTION_VAR_NAME, file))

    def __write_to_log(self, line: str):
        """
        Writes the line to the log of the BatchProcessor on a new line.
        :param line: The line to be written to the log
        """
        with open(self._log_file, "a") as f:
            f.write(line + "\n")

    @staticmethod
    def __mel_log(comment: str, result: bool = True):
        """
        Logs a comment using MEL. Will be displayed in the command response bar.
        :param comment: The comment to be displayed.
        :param result: Whether the line is the result of an action or process. Will display "Result: " in front.
        """
        mel.eval(f'print "{"Result: " if result else ""} {comment}\\n"')

    @staticmethod
    def error_message(fn, text: str, icn: str = "critical", title: str = "ERROR", *args, **kwargs):
        """
        Creates an error prompt and reruns the given function with arguments.

        :param fn: The function to run after the error message has been closed.
        :param text: The message to be shown in the error prompt.
        :param icn: The icon to be shown in the prompt. Default value is "critical", other options are "warning",
        "information" and "question"
        :param title: The title of the error prompt.
        :param args: Extra args given to the function.
        :param kwargs: Extra kwargs given to the function.
        """
        cmds.confirmDialog(icn=icn, message=text, b="Close", title=title)
        fn(*args, **kwargs)

    # Helper inner class for file structure.
    class FileTree(object):
        """
        A class representing a file tree.
        """
        def __init__(self, root: str, depth: int, layout: str, folder: bool = True, parent=None):
            """
            Creates a FileTree object, which represents a folder structure.
            :param root: The root path of the folder.
            :param depth: The depth of the folder.
            :param layout: The parent layout in which the folder structure is shown.
            :param folder: True if the structure is a folder, false if it represents a file.
            :param parent: The parent tree of this FileTree.
            """

            # Initialise values
            self.__root = root                      # The root path of the FileTree node
            self.name = os.path.basename(root)      # The display name of the FileTree node.
            self.depth = depth                      # The depth of the FileTree node in the root FileTree.
            self.__collapsed = False                # Whether the FileTree node is currently collapsed.
            self.__filtered = False                 # Whether the FileTree is filtered out.
            self._children = []                     # The children of the FileTree node.
            self.__parent = parent                  # The parent of the FileTree node.
            self.bolded = False                     # Whether the name's look should be altered. (Bold or Oblique)
            self.included = True                    # Whether the FileTree node and its children should be included.

            # If not the root, create the ui for it. Else create a row layout, also creating some space at the top.
            if depth > 0:
                self.ui = self.__create_ui(folder, layout)
            else:
                self.ui = cmds.rowLayout(h=5)
                cmds.setParent("..")

        def __create_ui(self, folder: bool, parent: str) -> str:
            """
            Creates a row layout UI of the FileTree.
            :param folder: True if the structure is a folder, false if it represents a file.
            :param parent: The parent layout in which the UI needs to be displayed.
            :return: A row layout with a dropdown option, a checkbox and a label.
            """

            # Creates the overarching row layout.
            layout = cmds.rowLayout(p=parent, nc=3, adjustableColumn=3, cw=[1, 20])

            # If it is a folder, make it collapsible.
            if folder:
                self.icon = cmds.iconTextButton(style='iconOnly', image1='arrowDown.png', align='center', w=20)
                cmds.iconTextButton(self.icon, e=True, command=self._collapse)
                cmds.rowLayout(layout, e=True, h=20, bgc=[0.1, 0.1, 0.13])

            # Create a checkbox for the lay-out.
            self.checkbox = cmds.checkBox(v=True, l="", height=15)
            self.label = cmds.text(label=self.name, align="left", font="plainLabelFont")
            cmds.checkBox(self.checkbox, e=True, cc=lambda _: self.include())
            return layout

        def _collapse(self) -> None:
            """
            Toggles the collapse of the underlying folder structure.
            """

            # Set the collapse-related attributes
            hidden = not self.__collapsed
            collapse_img = 'arrowRight.png' if hidden else 'arrowDown.png'
            cmds.iconTextButton(self.icon, e=True, image1=collapse_img)
            self.__collapsed = hidden

            # Go down the tree to hide everything.
            for ch in self._children:
                ch.hide(hidden)

        def hide(self, hidden: bool = False) -> None:
            """
            Hides or shows the UI of the FileTree.
            :param hidden: A boolean representing whether the FileTree should be hidden.
            """

            self.__collapsed = hidden
            status = not hidden and not self.__filtered
            cmds.rowLayout(self.ui, e=True, visible=status)

            # Also hide the children.
            for ch in self._children:
                ch.hide(hidden)

        def set_included(self, state: bool):
            """
            Sets the included state to the given. Will turn the label bold if turned off, otherwise makes it plain.
            :param state: Whether the root should be enabled or not.
            """
            cmds.checkBox(self.checkbox, e=True, value=state)
            self.included = state

            if not state:
                cmds.text(self.label, e=True, font="boldLabelFont")
                self.bolded = True
            else:
                cmds.text(self.label, e=True, font="plainLabelFont")
                self.bolded = False

        def include(self) -> None:
            """
            Sets the included value of the entire FileTree to the checkbox value of the root.
            """
            self.included = cmds.checkBox(self.checkbox, q=True, value=True)
            if not self.included:
                cmds.text(self.label, e=True, font="boldLabelFont")
                self.bolded = True
            else:
                cmds.text(self.label, e=True, font="plainLabelFont")
                self.bolded = False

            # Also include its children.
            for ch in self._children:
                ch.include_children(self.included)

            # Re-enable the parent if excluded.
            if self.depth > 1:
                self.__parent.child_include(self.included)

        def include_children(self, state: bool) -> None:
            """
            Sets the included value of the entire FileTree to the given state.
            :param state: Boolean to set the included to.
            """
            self.set_included(state)

            # Also set the children
            for ch in self._children:
                ch.include_children(self.included)

        def child_include(self, state: bool = True) -> None:
            """
            A child got set to be (not) included. Sets the parent to as well if the value got changed. If the child was
            ticked off, the parent will check whether all children have been turned oof before unchecking itself.
            """

            change_state = self.included != state
            plain_font = state

            # Check whether all children were excluded
            if not state:
                for ch in self._children:
                    if ch.included:
                        change_state = False
                        break
            else:
                for ch in self._children:
                    if ch.bolded:
                        plain_font = False
                        break

            # Change the state if necessary
            if change_state:
                self.set_included(state)

                if not plain_font and state:
                    cmds.text(self.label, e=True, font="obliqueLabelFont")
                    self.bolded = True

                if self.depth > 1:
                    self.__parent.child_include(state)

            else:
                if not plain_font:
                    cmds.text(self.label, e=True, font="obliqueLabelFont")
                    self.bolded = True
                else:
                    cmds.text(self.label, e=True, font="plainLabelFont")
                    self.bolded = False

        def filter(self, filter_field: str, error_field: str):
            """
            Filters the file tree on the string in the given filter field.
            :param filter_field: The field to check the string from.
            :param error_field: The error field to be shown if no files match the filter.
            """
            # Get the filter string out and set the filtered.
            self.__filtered = filter_field == ""
            filter_str = cmds.textField(filter_field, q=True, text=True)

            # Filters the children
            hidden = False
            for ch in self._children:
                hidden = ch.filter_str(filter_str)

            # Setting the error field in case all are hidden.
            cmds.text(error_field, e=True, visible=hidden)

        def filter_str(self, filter_str: str):
            """
            Filters the children with the given string
            :param filter_str: The string to filter on
            :return True if the FileTree did not get filtered out and a file was found.
            """
            # Directories
            if len(self._children) > 0:
                # Check all children
                hidden = True
                if self.__collapsed:
                    self._collapse()
                for ch in self._children:
                    hidden = ch.filter_str(filter_str) and hidden

                # Hide or show the folder depending on whether anything was found in its children.
                self.__filtered = hidden
                if not hidden:
                    cmds.rowLayout(self.ui, e=True, visible=True)
                else:
                    cmds.rowLayout(self.ui, e=True, visible=False)
                return hidden

            # Files
            else:
                # Check whether the files contain the filter string and (un)hide the UI accordingly.
                if filter_str.casefold() not in self.name.casefold():
                    self.__filtered = True
                    cmds.rowLayout(self.ui, e=True, visible=False)
                    return True
                else:
                    self.__filtered = False
                    cmds.rowLayout(self.ui, e=True, visible=True)
                    return False

        def add_filter_children(self):
            """
            Add the filtered files to the selection.
            """
            # Directories
            if len(self._children) > 0:
                for ch in self._children:
                    ch.add_filter_children()
                if self.depth > 1:
                    self.__parent.child_include(True)
            # Files
            else:
                if not self.__filtered:
                    self.set_included(True)
                    self.__parent.child_include(True)

        def add_filter(self, button):
            """
            Sets the filter and immediately adds the children to the field.

            :param button: The button connected to the filter addition
            """
            cmds.setFocus(button)
            self.add_filter_children()

        def set_to_filter(self, button):
            """
            Sets the selection equal to the filter.
            :param button: The button connected to the action.
            """
            self._children[0].include_children(False)
            self.add_filter(button)

        def prune_fbx(self, state) -> bool:
            """
            Disables and enables non-fbx files throughout the whole tree.
            :param state: If True, non-fbx files get disabled.
            :return: True if the top level got pruned.
            """

            pruned = state
            # For directories, check the children.
            if len(self._children) > 0:
                for ch in self._children:
                    pruned = ch.prune_fbx(state) and pruned
                if self.depth > 0:
                    cmds.checkBox(self.checkbox, e=True, en=not pruned)
                return pruned

            # Files
            else:
                if not self.name.endswith(".fbx"):
                    cmds.checkBox(self.checkbox, e=True, en=not pruned)
                    return pruned
                else:
                    return False

        def add_child(self, child):
            """
            Adds a child to the FileTree at top-level.
            :param child: The FileTree child to be added.
            """
            self._children.append(child)

        def get_all_included_files(self) -> [str]:
            """
            Get all the included and enabled leaf node roots of the FileTree. Does not keep filtered into account.
            :return: An array containing all the roots of leaf nodes flagged as included that are enabled.
            """
            enabled = True
            if self.depth > 0:
                enabled = cmds.checkBox(self.checkbox, q=True, en=True)

            # Don't go down the children if parent not enabled or included.
            if not self.included or not enabled:
                return []

            # Create the array
            tree = []
            if len(self._children) > 0:
                for ch in self._children:
                    tree += ch.get_all_included_files()
            else:
                tree.append(self.__root)

            return tree

        # Helper functions within helper class for testing purposes.
        def get_all_children(self) -> []:
            """
            Returns all the nodes of the FileTree in a list.
            :return: A flat array containing all nodes in the FileTree
            """
            tree = []
            for ch in self._children:
                tree += ch.print_children()
            tree.append(self)
            return tree

        def get_tree_array(self) -> []:
            """
            Returns the FileTree as a nested array with the same structure as the FileTree containing the roots
            :return: An array version of the FileTree containing the roots.
            """
            tree = []
            for ch in self._children:
                tree.append(ch.print_children())
            tree.append(self.__root)
            return tree

    # ################################################################### #
    # ################### Actual BatchProcessor stuff ################### #

    # ############################################## #
    # ################### LAYOUT ################### #

    def __create_window(self) -> None:
        """
        Creates the BatchProcessor window if none yet exist. Otherwise, will set the focus on the already existing
        window.
        """
        # Create the window and set up the master layout.
        cmds.window("AssetLibraryBatchProcessor", t="Asset Library Batch Processor", widthHeight=(900, 535),
                    cc=self.close)
        master_layout = cmds.columnLayout(adj=True, rs=15)

        # Setup of the two sides of the main layout. Left for the files and Right for the options
        main_layout = cmds.formLayout()
        file_layout = self.__create_file_layout(main_layout)
        separator = cmds.separator(hr=False, style="out", p=main_layout)
        settings_layout = self.__create_settings_layout(main_layout)

        cmds.formLayout(main_layout, e=True,
                        attachForm=[(file_layout, "left", 10), (file_layout, "top", 10),
                                    (settings_layout, "right", 15), (settings_layout, "top", 10),
                                    (separator, "top", 10), (separator, "bottom", 5)],
                        attachControl=[(file_layout, "right", 15, separator),
                                       (separator, "right", 15, settings_layout)])

        # Set up the bottom buttons: Run and Close
        cmds.setParent(master_layout)
        cmds.separator(style="out")
        button_layout = cmds.formLayout()
        run_button = cmds.button(l="Run", w=50, h=22)
        cmds.button(run_button, e=True, c=lambda _: self.__run_processor())
        cancel_button = cmds.button(l="Close", c=lambda _: self.cancel(), w=60, h=22)
        cmds.formLayout(button_layout, e=True, attachForm=[(cancel_button, "right", 10)],
                        attachControl=[(run_button, "right", 10, cancel_button)])

    def __create_file_layout(self, main_layout: str) -> str:
        """
        Creates the File layout. This contains the source file system as well as the search.
        :param main_layout: The parent layout to which this layout should be parented.
        :return: Returns the name of the column layout containing the file layout.
        """
        # Create the File system lay-out
        file_layout = cmds.columnLayout(adj=True, rs=0, p=main_layout)
        cmds.frameLayout(label=f"SOURCE FILES", p=file_layout)

        # -- Setup of the Source selection -- #

        target = cmds.formLayout(h=45)
        target_label = cmds.text(l="Source:", font="boldLabelFont", h=20)
        target_field = cmds.textField(h=20, ed=False, bgc=[0.2, 0.2, 0.2], w=300)
        target_browse = cmds.button(l="Browse", h=20)

        # Setup of the form layout
        cmds.formLayout(target, e=True, attachForm=[(target_label, "left", 10), (target_browse, "right", 5),
                                                    (target_label, "top", 16), (target_field, "top", 16),
                                                    (target_browse, "top", 15)],
                        attachControl=[(target_field, "left", 15, target_label),
                                       (target_field, "right", 8, target_browse)])

        cmds.button(target_browse, e=True, c=lambda _: self.source_browse(target_field))

        cmds.separator(p=file_layout, h=15)

        # -- Setup of the File System Layout -- #

        self.__files_scroll = cmds.scrollLayout(w=350, h=300, cr=True, vsb=True, p=file_layout, bgc=[0.2, 0.2, 0.2])
        filter_error = cmds.text(l="No files containing the filter string were found.", visible=False)
        self.__files_layout = cmds.formLayout()
        self._update_all_files(self._root, target_field)

        cmds.separator(p=file_layout, h=15)

        # -- Setup of the Search bar -- #

        search = cmds.formLayout(p=file_layout)
        search_label = cmds.text(l="Search files:", font="boldLabelFont", h=20)
        search_field = cmds.textField(h=20)
        cmds.textField(search_field, e=True, cc=lambda _: self.__folder_structure.filter(search_field, filter_error))

        # Buttons adding entire filter to the selection at once.
        add_sel_filter_button = cmds.button(l="Add search to selection")
        cmds.button(add_sel_filter_button, e=True,
                    c=lambda _: self.__folder_structure.add_filter(add_sel_filter_button))
        sel_filter_button = cmds.button(l="Set selection to search")
        cmds.button(sel_filter_button, e=True, c=lambda _: self.__folder_structure.set_to_filter(sel_filter_button))

        # Set up the form layout
        cmds.formLayout(search, e=True, attachForm=[(search_label, "left", 10), (search_field, "right", 5),
                                                    (search_label, "top", 0), (search_field, "top", 0),
                                                    (sel_filter_button, "right", 5),
                                                    (add_sel_filter_button, "bottom", 5),
                                                    (sel_filter_button, "bottom", 5)],
                        attachControl=[(search_field, "left", 15, search_label),
                                       (sel_filter_button, "top", 7, search_field),
                                       (add_sel_filter_button, "right", 5, sel_filter_button),
                                       (add_sel_filter_button, "top", 7, search_field)])

        return file_layout

    def __create_settings_layout(self, main_layout: str) -> str:
        """
        Creates the settings layout. Contains all settings pertaining to
        the actual processes when running over the batch.
        :param main_layout: The layout to which the settings layout should be parented.
        :return: Returns the name of the column layout containing the settings layout.
        """
        # Main layout of the settings
        settings_layout = cmds.columnLayout(adj=True, p=main_layout)
        cmds.frameLayout(l="PROCESSES", w=350)

        # Setup of the picking of a Target directory.
        target = cmds.formLayout(h=50)
        target_label = cmds.text(l="Target:", font="boldLabelFont", h=20)
        target_field = cmds.textField(h=20, ed=False, bgc=[0.2, 0.2, 0.2], text=self._dest)
        target_browse = cmds.button(l="Browse", h=20)
        cmds.formLayout(target, e=True, attachForm=[(target_label, "left", 10), (target_browse, "right", 5),
                                                    (target_label, "top", 16), (target_field, "top", 16),
                                                    (target_browse, "top", 15)],
                        attachControl=[(target_field, "left", 15, target_label),
                                       (target_field, "right", 8, target_browse)])

        # -- Setup of the export settings layout -- #

        export_layout = cmds.frameLayout(l="Export Settings", cll=True, p=settings_layout, cl=True)
        self.create_export_frame(export_layout)
        cmds.button(target_browse, e=True, c=lambda _: self.target_browse(target_field))

        cmds.separator(p=settings_layout, h=25)

        # -- Setup of the process setting layouts -- #

        # Setup of the pivot frame
        (pivot, pivot_frame) = self.create_process_container(settings_layout, "Pivot")
        pivot_inner = self.create_pivot_frame(pivot_frame)
        cmds.checkBox(pivot, e=True, v=self.pivot, cc=lambda state: self.set_pivot(state, pivot_inner))
        self.set_pivot(self.pivot, pivot_inner)

        # Setup of the scaling frame
        cmds.setParent(settings_layout)
        (scale, scale_frame) = self.create_process_container(settings_layout, "Scaling")
        scale_inner = self.create_scale_frame(scale_frame)
        cmds.checkBox(scale, e=True, v=self.scaling, cc=lambda state: self.set_scaling(state, scale_inner))
        self.set_scaling(self.scaling, scale_inner)

        return settings_layout

    @staticmethod
    def create_process_container(parent: str, label: str) -> (str, str):
        """
        Creates a frame layout with a checkbox for process settings.
        :param parent: The parent of the new layout.
        :param label: The label displayed in the new frame layout.
        :return: Returns a tuple containing the name of the checkbox and the name of the frame layout.
        """
        form_layout = cmds.formLayout(p=parent)
        checkbox = cmds.checkBox(v=True, l="", w=30)
        frame_layout = cmds.frameLayout(l=label, cll=True)
        cmds.formLayout(form_layout, e=True, attachForm=[(checkbox, "left", 0), (frame_layout, "top", 0),
                                                         (checkbox, "top", 4), (frame_layout, "right", 0),
                                                         (frame_layout, "bottom", 8)],
                        attachControl=[(frame_layout, "left", 5, checkbox)])
        return checkbox, frame_layout

    def create_pivot_frame(self, frame: str) -> str:
        """
        Creates the layout for the pivot settings.
        :param frame: The parent frame layout.
        :return: Returns the name of the column layout containing the pivot layout.
        """
        pivot_master = cmds.columnLayout(p=frame, adj=True)

        cmds.text(l="Set the pivot location of the meshes relative to the object's \nbounding box:", align="left",
                  w=350)
        cmds.rowLayout(h=5, nc=1)
        cmds.setParent("..")

        # Create the options with radio buttons and set up the commands.
        options = ["Min", "Middle", "Max"]
        pivot_x = self.create_radio_group("X", pivot_master, options, default_opt=self.pivot_placement[0])
        pivot_y = self.create_radio_group("Y", pivot_master, options, default_opt=self.pivot_placement[1])
        pivot_z = self.create_radio_group("Z", pivot_master, options, default_opt=self.pivot_placement[2])
        for i in range(3):
            cmds.iconTextRadioButton(pivot_x[i], e=True, onc=lambda _, j=i: self.set_pivot_placement(0, j))
            cmds.iconTextRadioButton(pivot_y[i], e=True, onc=lambda _, j=i: self.set_pivot_placement(1, j))
            cmds.iconTextRadioButton(pivot_z[i], e=True, onc=lambda _, j=i: self.set_pivot_placement(2, j))
        cmds.rowLayout(h=5, p=pivot_master)

        return pivot_master

    @staticmethod
    def create_radio_group(label: str, layout: str, options: [str], default_opt: int = 1, label_width: int = 50,
                           align: str = "center", width: int = 80) -> [str]:
        """
        Creates a group of radio-like buttons with the given options.
        :param label: The label in front of the radio buttons.
        :param layout: The parent layout.
        :param options: The labels for the possible buttons.
        :param default_opt: The default selected index from 0 to len - 1.
        :param label_width: The width of the label.
        :param align: The alignment of the label.
        :param width: The buttons' width.
        :return: An array with the buttons created.
        """
        cmds.rowLayout(nc=4, p=layout)
        cmds.text(l=label, w=label_width, h=20, align=align)

        radio_collection = cmds.iconTextRadioCollection()
        buttons = []
        for opt in options:
            button = cmds.iconTextRadioButton(st='textOnly', l=opt, w=width, bgc=[0.4, 0.4, 0.4], h=20)
            buttons.append(button)
        cmds.iconTextRadioCollection(radio_collection, e=True, select=buttons[default_opt])
        return buttons

    def create_scale_frame(self, frame: str) -> str:
        """
        Creates the layout for the scale settings.
        :param frame: The layout to parent the new layout to.
        :return: The name of the column layout containing the scaling layout.
        """
        scale_master = cmds.columnLayout(p=frame, adj=True)
        cmds.text(l="Set the grid scale of the meshes. Meshes will be scaled up or \n"
                    "down towards the nearest grid point that is not zero:", align="left", w=350)
        button_width = 80

        # -- Creation of the form layout -- #
        checkbox_layout = cmds.formLayout(p=scale_master)

        # Layout in case of stretching allowed
        scale_row = cmds.columnLayout(adj=True, p=checkbox_layout, visible=self.allow_stretching)
        cmds.rowLayout(nc=4)
        cmds.text(l="Scaling", w=50, h=20)
        scale_x = cmds.textField(w=button_width, text=self.scale[0])
        cmds.textField(scale_x, e=True, cc=lambda u_input: self.check_text_fields(scale_x, u_input, 0))
        scale_y = cmds.textField(w=button_width, text=self.scale[1])
        cmds.textField(scale_y, e=True, cc=lambda u_input: self.check_text_fields(scale_x, u_input, 1))
        scale_z = cmds.textField(w=button_width, text=self.scale[2])
        cmds.textField(scale_z, e=True, cc=lambda u_input: self.check_text_fields(scale_x, u_input, 2))

        # Layout in case of no stretching allowed
        non_stretch = cmds.columnLayout(p=checkbox_layout, visible=not self.allow_stretching)
        scale_axis = self.create_radio_group("Main Axis", non_stretch, ["X", "Y", "Z"], self.main_axis, 60, "left", 70)
        for i in range(3):
            cmds.iconTextRadioButton(scale_axis[i], e=True, onc=lambda _, j=i: self.set_main_axis(j))
        cmds.rowLayout(nc=2, p=non_stretch)
        cmds.text(l="Scaling", w=58, h=22, align="left")
        scale_txt = cmds.textField(w=75, text="50")
        cmds.textField(scale_txt, e=True, cc=lambda u_input: self.check_text_fields(scale_txt, u_input, 3))

        # Setup checkbox and form layout
        allow_stretching = cmds.checkBox(v=self.allow_stretching, l="Allow stretching of meshes", p=checkbox_layout)
        cmds.checkBox(allow_stretching, e=True, cc=lambda state: self.set_stretching(state, scale_row, non_stretch))

        cmds.formLayout(checkbox_layout, e=True, attachForm={(scale_row, "left", 12), (allow_stretching, "top", 8),
                                                             (allow_stretching, "left", 4), (scale_row, "right", 20),
                                                             (non_stretch, "left", 18), (non_stretch, "right", 20)},
                        attachControl={(scale_row, "top", 5, allow_stretching),
                                       (non_stretch, "top", 5, allow_stretching)})
        return scale_master

    def create_export_frame(self, frame: str):
        """
        Creates the layout for the export settings.
        :param frame: The parent of the layout.
        """
        export_layout = cmds.formLayout(p=frame)

        # Create the options
        fbx_only = cmds.checkBox(v=not self.fbx_only, l="Also copy non-fbx files", p=export_layout,
                                 cc=lambda state: self.set_prune_fbx(not state))
        self.set_prune_fbx(self.fbx_only)

        own_fbx = cmds.checkBox(v=self.own_fbx, l="Give each mesh its own fbx file", p=export_layout,
                                cc=lambda state: self.set_own_fbx(state), en=not self.combine_meshes)
        combine_meshes = cmds.checkBox(v=self.combine_meshes, l="Combine meshes", p=export_layout,
                                       cc=lambda state: self.set_combine(state, own_fbx))

        # Setup of the form layout
        cmds.formLayout(export_layout, e=True, attachForm={(fbx_only, "left", 20), (fbx_only, "top", 5),
                                                           (fbx_only, "right", 20), (combine_meshes, "left", 20),
                                                           (combine_meshes, "right", 20), (own_fbx, "left", 45),
                                                           (own_fbx, "bottom", 0)},
                        attachControl={(combine_meshes, "top", 5, fbx_only), (own_fbx, "top", 0, combine_meshes)})

    # ################################################# #
    # ################ BUTTON COMMANDS ################ #

    def source_browse(self, field: str):
        """
        Browse for a new source location.
        :param field: The text field in which the source path should be displayed.
        """
        # Ask for a new source location
        new_source_lst = cmds.fileDialog2(ds=1, fm=3, dir=self._root)

        # Check the source location
        if new_source_lst is not None:
            new_source = new_source_lst[0]
            no_error = self.check_source(new_source, lambda: self.source_browse(field))

            if no_error:
                self._update_all_files(new_source, field)

    def target_browse(self, field: str):
        """
        Browse for a new target location.
        :param field: The text field in which the target path should be displayed.
        """

        # Ask for a destination location
        start_dir = self._dest if self._dest != "" else self._root
        new_dest_lst = cmds.fileDialog2(ds=1, fm=3, dir=start_dir)

        # Check the given location
        if new_dest_lst is not None:
            new_dest = new_dest_lst[0]
            no_error = self.check_dest(new_dest, lambda: self.target_browse(field))

            if no_error:
                self._dest = new_dest
                self.dest_changed = True
                cmds.textField(field, e=True, text=new_dest)

    def set_stretching(self, state, ui_true, ui_false):
        """
        Sets whether the Processor allows stretching of the fbx objects.
        :param state: True if stretching is allowed
        :param ui_true: The UI to show if stretching is allowed.
        :param ui_false: The UI to show if stretching is not allowed.
        """
        self.allow_stretching = state
        cmds.columnLayout(ui_true, e=True, visible=state)
        cmds.columnLayout(ui_false, e=True, visible=not state)

    def set_prune_fbx(self, fbx_only: bool = True):
        """
        Sets whether the Processor will prune non-fbx files.
        :param fbx_only: If true, all non-fbx files will be disabled.
        """
        self.fbx_only = fbx_only
        self.__folder_structure.prune_fbx(fbx_only)

    def set_combine(self, state, own_fbx_layout):
        """
        Sets whether the Processor combines all meshes within one fbx file.
        :param state: True if meshes should be combined.
        :param own_fbx_layout: The checkbox pertaining to whether all objects within an fbx should have their own file.
        """
        self.combine_meshes = state
        cmds.checkBox(own_fbx_layout, e=True, en=not state)

    def set_own_fbx(self, state):
        """
        Sets whether the Processor will create separate fbx files for each object within one fbx file.
        :param state: True if separate fbx files are wanted.
        """
        self.own_fbx = state

    def set_scaling(self, state, inner):
        """
        Sets whether the Processor will scale its processed objects.
        :param state: True if meshes should be scaled.
        :param inner: The layout containing the scale settings.
        """
        self.scaling = state
        cmds.columnLayout(inner, e=True, en=state)

    def set_pivot(self, state, inner):
        """
        Sets whether the Processor will adjust the pivot of its processed objects.
        :param state: True if pivots should be adjusted.
        :param inner: The layout containing the pivot settings.
        """
        self.pivot = state
        cmds.columnLayout(inner, e=True, en=state)

    def set_pivot_placement(self, axis, pivot_type):
        """
        Sets the preferred placement of the pivot relative to the objects.
        :param axis: Which axis needs to be adjusted
        :param pivot_type: Where the pivot needs to be placed: 0 = min, 1 = middle, 2 = max.
        """
        self.pivot_placement[axis] = pivot_type

    def set_main_axis(self, axis):
        """
        Sets the main axis the Processor will use for scaling in the case that stretching is not allowed.
        :param axis: The new main axis.
        """
        self.main_axis = axis

    # ################################################# #
    # ################## USER CHECKS ################## #

    def check_source(self, root: str, fn, *args, **kwargs):
        """
        Checks the source location. For the source location to be correct, it needs to contain at least one fbx file. If
        the source location is not valid, it will call the function given.
        :param root: The root path of the source folder structure.
        :param fn: The function to be called in case the source is not correct.
        :param args: Extra args to be given to the function.
        :param kwargs: Extra kwargs to be given to the function.
        :return: True if the source location is good for use.
        """
        sub_folder_walk = os.walk(root)
        for root, dirs, files in sub_folder_walk:
            for f in files:
                if f.endswith(".fbx"):
                    return True
        else:
            self.error_message(fn, "Please choose a folder structure containing at least one fbx file", *args, **kwargs)
            return False

    def check_dest(self, root, fn, *args, **kwargs):
        """
        Checks the destination location. A destination location is correct if it is not empty and the user has write
        access. Will give a warning if the destination already contains an output folder.
        :param root: The path of the destination folder.
        :param fn: The function to be called if the destination is not good for use.
        :param args: Extra args to be given to the function above.
        :param kwargs: Extra kwargs to be given to the function above.
        :return: True if the destination location can be used, otherwise False.
        """
        # Destination is not empty.
        if root is "":
            self.error_message(fn, "No target folder was set. Please select one.",
                               *args, **kwargs)
            return False

        # Have write access in the given destination.
        path = os.path.join(root, "_output")
        if not os.access(root, os.W_OK):
            self.error_message(fn, "No permission to write in this folder. Please choose a different destination.",
                               *args, **kwargs)
            return False

        # Throw a warning if an output folder already exists.
        if os.path.exists(path):
            dialog = cmds.confirmDialog(message="There is already an output folder (/_output) at this destination. \n"
                                                "\nThis tool will overwrite any duplicate files. If this is not wanted,"
                                                "\n please choose a different directory.",
                                        button=["Choose new directory", "Continue"],
                                        title="WARNING", ma="left", icn="warning")
            if dialog == "Choose new directory":
                fn(*args, **kwargs)
                return False
        return True

    def check_text_fields(self, text_field, u_input, index: int):
        """
        Checks and resets scaling text fields to only contain float values.
        :param text_field: The text field to be checked.
        :param u_input: The input the user gave.
        :param index: The axis whose scale got adjusted. Equals 3 in case no stretching is allowed.
        """
        try:
            scale = float(u_input)
            if scale > 0.01:
                self.scale[index] = scale
            else:
                self.scale[index] = 0.01
                cmds.textField(text_field, e=True, text="0.01")
        except ValueError:
            cmds.textField(text_field, e=True, text=str(self.scale[index]))

    # ################################################# #
    # ################### PROCESSES ################### #

    def run(self) -> None:
        """
        Run the BatchProcessor.
        """
        cmds.showWindow(self._window)
        self.__mel_log("Opened Batch Processor")

    def cancel(self) -> None:
        """
        Closes the window.
        """
        cmds.setFocus(self._window)
        cmds.deleteUI(self._window)

    def close(self) -> None:
        """
        Runs when the window gets deleted. Saves preferences and logs the exit of the window.
        """
        self.__save_prefs()
        self.__mel_log("Exited Batch Processor")

    def _update_all_files(self, directory: str, source_field: str) -> None:
        """
        Updates all the files in the file system to have the given directory as root.
        :param directory: The new root of the file system.
        """

        # -- Set up the base structure -- #

        self._root = directory
        cmds.deleteUI(self.__files_layout)
        self.__files_layout = cmds.formLayout(p=self.__files_scroll)
        self.__folder_structure = self.FileTree(self._root, 0, self.__files_layout)

        parent_folders = [self.__folder_structure]
        last_ui = self.__folder_structure.ui
        folder_amount = [1]

        # -- Create the Tree -- #

        file_iterator = os.walk(self._root)
        for root, dirs, files in file_iterator:
            # Get the parent and depth right
            last_folder = parent_folders[-1]
            depth = last_folder.depth + 1

            # Create our root folder in our tree structure
            new_folder = self.FileTree(root, depth, self.__files_layout, parent=last_folder)
            last_folder.add_child(new_folder)
            self.set_file_sys_frame(new_folder, last_ui)
            last_ui = new_folder.ui

            # Add all the files in this folder to this folder
            for f in files:
                path = os.path.join(root, f)
                child_tree = self.FileTree(path, depth + 1, self.__files_layout, False, new_folder)
                new_folder.add_child(child_tree)
                self.set_file_sys_frame(child_tree, last_ui)
                last_ui = child_tree.ui

            # If this directory has sub-folders, add the directory to the parents
            if len(dirs) != 0:
                parent_folders.append(new_folder)
                folder_amount.append(len(dirs))
            else:
                # If the parent folder has no more sub-folders, go one dir up.
                folder_amount[-1] -= 1
                while folder_amount[-1] == 0:
                    folder_amount.pop()
                    parent_folders.pop()
                    if len(parent_folders) == 0:
                        break
                    folder_amount[-1] -= 1

        # Set the source text field to the root.
        cmds.textField(source_field, e=True, text=self._root)

    def set_file_sys_frame(self, tree: FileTree, last_ui: str) -> None:
        """
        Adds the FileTree root node to the UI.
        :param tree: The FileTree of which the root needs to be added.
        :param last_ui: The node above this one in the window.
        """
        cmds.formLayout(self.__files_layout, e=True,
                        attachForm=[(tree.ui, 'left', tree.depth * 20 - 15), (tree.ui, 'right', 10)],
                        attachControl=[(tree.ui, 'top', 0, last_ui)])

    def __run_processor(self) -> None:
        """
        Running the actual processing of the BatchProcessor.
        """
        # Make sure all user input went through and got checked.
        cmds.setFocus(self._window)
        if not self.dest_changed:
            if not self.check_dest(self._dest, lambda *args: None):
                return
        if not self.check_source(self._root, lambda *args: None):
            return

        # Get the selected files.
        files = self.__folder_structure.get_all_included_files()

        if len(files) == 0:
            self.error_message(lambda *args: None, "No files were selected.", title="Runtime Error")
            return

        # Do the processing thingies for every file.
        root_len = len(self._root)
        base_path = os.path.join(self._dest, "_output")

        # Setup log file
        self._log_file = os.path.join(base_path, "log.txt")
        self.__write_to_log(f"{time.asctime()}: Processing of {len(files)} files. \n")
        timestamp = time.time()

        process_text, process_bar, button = self.__show_progress(len(files))

        # -- Processing -- #

        i = 0
        warnings = 0
        for f in files:
            # -- Create folder structure necessary for the file -- #

            # Set up the folder structure within the output folder
            directory = os.path.dirname(f)
            directory = directory[root_len+1:]
            directory = os.path.join(base_path, directory)

            # Create directory in the output folder if not yet existent
            if not os.path.exists(directory):
                os.makedirs(directory)
            file_name = os.path.basename(f)
            path = os.path.join(directory, file_name)

            # -- Do stuff with the file -- #

            short_path, ext = os.path.splitext(path)
            fbx_obj = []
            if ext == ".fbx":
                # Get a selection of the files loaded in.
                in_scene = cmds.ls(dag=True)
                cmds.file(f, i=True)
                for obj in cmds.ls(dag=True):
                    if obj not in in_scene:
                        fbx_obj.append(obj)

                # Combine the meshes if wanted
                if self.combine_meshes:
                    fbx_obj = cmds.polyUnite(fbx_obj)
                    cmds.delete(fbx_obj, constructionHistory=True)

                # Processes
                if self.scaling:
                    warnings += self.__adjust_dimensions(fbx_obj, f)
                if self.pivot:
                    self.__adjust_pivots(fbx_obj)

                warnings += self.__write_file(fbx_obj, short_path)

                # Clean up the maya scene
                fbx_obj = cmds.ls(fbx_obj, dag=True)
                cmds.delete(fbx_obj)

            else:
                # Copy non-fbx files the normal way.
                if os.path.exists(path):
                    warnings += 1
                    self.__write_to_log(f"-- WARNING: {path} already existed. Original contents overridden.")
                shutil.copy2(f, path)

            # Update the progress bar and make sure files got properly written out
            i += 1
            self.__update_progress(process_text, process_bar, button, warnings)
            cmds.flushIdleQueue()

        # Final notes for the user.
        time_elapsed = time.time() - timestamp
        self.__mel_log(f"Files Processed: {i} out of {len(files)}")
        self.__write_to_log(f"\n Processing {i} out of {len(files)} finished in {time_elapsed} seconds with "
                            f"{warnings} warnings. \n")

    def __adjust_pivots(self, fbx: [str]):
        """
        Adjusts the pivots of the given objects to the Processor's settings.
        :param fbx: The names of the objects in the Maya scene to be adjusted.
        """
        fbx = cmds.ls(fbx, dag=True)
        for obj in fbx:
            bbox = cmds.exactWorldBoundingBox(obj)

            # Determine the new pivot placement in world space
            pivot = []
            for i in range(3):
                if self.pivot_placement[i] == 1:
                    pivot.append((bbox[i] + bbox[i + 3]) / 2)
                else:
                    pivot.append(bbox[int(self.pivot_placement[i]/2) * 3 + i])

            # Move the pivot to the right location.
            cmds.xform(obj, piv=pivot, ws=True)

            # Move to zero and "Bake" Pivot
            cmds.move(0, 0, 0, obj, a=True, scalePivotRelative=True)
            cmds.makeIdentity(obj, apply=True, t=1, r=1, s=1, n=0)

    def __adjust_dimensions(self, fbx: [str], f: str) -> int:
        """
        Adjusts the dimensions of the given object to the Processor's settings. Will log a warning in the case of heavy
        scaling or stretching.
        :param fbx: The names of the objects in the Maya scene to be adjusted.
        :param f: The original file path, to be used in the warning message.
        :return: The amount of warnings written out.
        """
        fbx = cmds.ls(fbx, dag=True)

        warnings = 0
        for obj in fbx:
            bbox = cmds.exactWorldBoundingBox(obj)
            cur_dimensions = [bbox[3] - bbox[0], bbox[4] - bbox[1], bbox[5] - bbox[2]]

            # Determine the grid to scale to.
            if self.allow_stretching:
                grid = self.scale[:3]
            else:
                grid = []
                for i in range(3):
                    grid.append(cur_dimensions[i] / cur_dimensions[self.main_axis] * self.scale[3])

            # Determine the scale needed and check for scaling/stretching.
            scale = []
            warning_grid = False
            warning_stretch = False
            for i in range(3):
                scale_dim = grid[i] / cur_dimensions[i] * max(round(cur_dimensions[i]/grid[i]), 1)
                scale.append(scale_dim)

                if not 0.55 < scale_dim < 1.45:
                    warning_grid = True

                for j in range(i):
                    stretch = scale[j] / scale[i]
                    if not 0.85 < stretch < 1.15:
                        warning_stretch = True

            # Log warnings if applicable.
            if warning_grid:
                self.__write_to_log(f"-- WARNING: {obj} in file {f} deviates far from the "
                                    f"grid with a scaling of {scale}.")
                warnings += 1

            if warning_stretch:
                self.__write_to_log(f"-- WARNING: {obj} in file {f} has severe stretching along its axes "
                                    f"with scaling of {scale}.")
                warnings += 1

            # Scale
            cmds.scale(scale[0], scale[1], scale[2], obj, ws=True, r=True)

        return warnings

    def __write_file(self, fbx: [str], path: str) -> int:
        """
        Will write out the objects from the Maya scene into the given directory according to the Processor's settings.
        Will write out a warning if a file already existed.
        :param fbx: The name of the objects to be written out to the fbx file(s)
        :param path: The directory to write the fbx files to.
        :return: The amount of warnings written out.
        """
        fbx = cmds.ls(fbx, dag=True, tr=True)
        warnings = 0

        # If all objects needed different files, create those.
        if self.own_fbx and not self.combine_meshes:
            for f in fbx:
                full_path = path + "_" + f + ".fbx"
                if os.path.exists(full_path):
                    warnings += 1
                    self.__write_to_log(f"-- WARNING: {full_path} already existed. Original contents overridden.")

                cmds.select(f)
                cmds.file(full_path, es=True, type="fbx export")
            return warnings

        # Otherwise, write everything to one file.
        path = path + ".fbx"
        if os.path.exists(path):
            warnings += 1
            self.__write_to_log(f"-- WARNING: {path} already existed. Original contents overridden.")
        cmds.select(fbx)
        cmds.file(path, es=True, type="fbx export")

        return warnings

    def __show_progress(self, max_value):
        """
        Creates the window showing the progress of the processor.
        :param max_value: The amount of files to be processed in total.
        :return: A tuple containing the text field, progress bar and button of the window.
        """
        # Create the window.
        if cmds.window(self.__progress_window, ex=True):
            cmds.showWindow(self.__progress_window)
        else:
            cmds.window(self.__progress_window, title="Processing in Progress", width=300, height=100)

        # Create the form layout
        form = cmds.formLayout()
        text = cmds.text(l=f"0/{max_value} Files Processed")
        bar = cmds.progressBar(h=30, max=max_value)
        button = cmds.button(l="Close", c=lambda _: cmds.deleteUI(self.__progress_window), vis=False)
        cmds.formLayout(form, e=True, attachForm={(text, "top", 10), (bar, "left", 25), (bar, "right", 25),
                                                  (text, "left", 5), (text, "right", 5), (button, "left", 150),
                                                  (button, "right", 150)},
                        attachControl={(bar, "top", 15, text), (button, "top", 25, bar)})
        cmds.showWindow(self.__progress_window)

        return text, bar, button

    @staticmethod
    def __update_progress(text, bar, button, warnings):
        """
        Ups the progress shown by the progress window by one.
        :param text: The textfield of the progress window.
        :param bar: The progress bar displayed by the progress window.
        :param button: The close button of the progress window.
        :param warnings: The amount of warnings logged.
        """
        nr = cmds.progressBar(bar, q=True, pr=True) + 1
        max_value = cmds.progressBar(bar, q=True, max=True)
        cmds.text(text, e=True, l=f"{nr}/{max_value} Files Processed")

        # If finished processing
        if nr == max_value:
            cmds.progressBar(bar, e=True, ep=True)
            cmds.button(button, e=True, vis=True)
            cmds.text(text, e=True, l=f"{nr} files processed with {warnings} warnings. \n"
                                      f"See the log for more information.")

        cmds.progressBar(bar, e=True, pr=nr)


# ############################################ #
# ################### MAIN ################### #

processor = BatchProcessor()
