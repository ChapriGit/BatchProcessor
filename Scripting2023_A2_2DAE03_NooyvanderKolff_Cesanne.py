import os
from maya import cmds


# Asset Library Batch Processor
# Requirements:
#     - Work with any folder structure
#     - For every mesh:
#           - Snap mesh dimensions to the nearest grid point
#           - Adjust all pivots to the specified space in the FBX (Center, bottom-left, bottom center, ...)
#           - Exclude, but still copy, files from processing: FBX only copy vs. all copy
#           - Log file: Keeps track of stuff that's been done (e.g. scale by extreme amount.)
#     - Script has thought-out visuals during the process
#     - Additional features
#     - Make preset file on first open? Then check?

# TODO:
# - Pivot
# - Scaling
# - Get the radiocollections input change
# - Run & User Checks especially on the textfields!
# - Log file
# - Set root folder

# - Set selection to search without search italic?

class BatchProcessor(object):
    def __init__(self):
        """
        Initialises a BatchProcessor object and runs the script.
        """
        # -- Setup variables to have a clear overview -- #

        # Start in current directory, have a button to change it.
        self._root = r"C:\Users\cnvdk\DocumentsHowest\Scripting_2\TestProject\src"  # The source folder.
        self._dest = ""                                                             # The destination folder.

        # TODO: Options
        # All variables to do with exporting and processing settings
        self.fbx_only = True                            # True if only fbx files get copied over.
        self.combine_meshes = True                      # True if wanting to combine meshes within one fbx file.
        self.own_fbx = False                            # Each mesh will get their own fbx if true. (Combine is False)
        self.pivot = True                               # True if pivot has to be changed.
        self.pivot_placement = [1, 1, 1]                # Pivot placement per axis: 0 = min, 1 = middle, 2 = max.
        self.scaling = True                             # True if scaling is wanted for the objects.
        self.scale_all = ["", "", ""]                   # The text fields containing the scaling to snap objects to.
        self.allow_stretching = True                    # True if models are allowed to be stretched.
        self.main_axis = 0                              # The main axis in case stretching is not allowed.
        self.scale = ""                                 # The text field containing the uniform scale.

        # TODO: Log file
        # The log file.
        self.log_file = ""

        # Window variables.
        self._window = "AssetLibraryBatchProcessor"     # The window.
        self.__files_layout = ""                        # The layout containing the file panel.
        self.files_scroll = ""                          # The scroll layout containing the tree view.
        self._folder_structure = None                   # The folder structure shown in the UI.

        # -- Create the window and run -- #
        self.__create_window()
        self.run()

    # ################################################################### #
    # ################## Helper Functions and Classes ################### #

    def __write_to_log(self, line: str):
        """
        Writes the line to the log of the BatchProcessor on a new line.
        :param line: The line to be written to the log
        """
        with open(self.log_file, "a") as f:
            f.write(line + "\n")

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
            self.root = root                        # The root path of the FileTree node
            self.name = os.path.basename(root)      # The display name of the FileTree node.
            self.depth = depth                      # The depth of the FileTree node in the root FileTree.
            self.collapsed = False                  # Whether the FileTree node is currently collapsed.
            self.included = True                    # Whether the FileTree node and its children should be included.
            self._children = []                     # The children of the FileTree node.
            self.__parent = parent                  # The parent of the FileTree node.
            self.bolded = False
            self.filtered = False

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
            hidden = not self.collapsed
            collapse_img = 'arrowRight.png' if hidden else 'arrowDown.png'
            cmds.iconTextButton(self.icon, e=True, image1=collapse_img)
            self.collapsed = hidden

            # Go down the tree to hide everything.
            for ch in self._children:
                ch.hide(hidden)

        def hide(self, hidden: bool = False) -> None:
            """
            Hides or shows the UI of the FileTree.
            :param hidden: A boolean representing whether the FileTree should be hidden.
            """

            self.collapsed = hidden
            status = not hidden and not self.filtered
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
            self.filtered = True
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
                hidden = []
                for ch in self._children:
                    hidden.append(ch.filter_str(filter_str))

                # Hide or show the folder depending on whether anything was found in its children.
                file_found = False in hidden
                self.filtered = not file_found
                if file_found:
                    if self.collapsed:
                        self._collapse()
                    cmds.rowLayout(self.ui, e=True, visible=True)
                else:
                    if not self.collapsed:
                        self._collapse()
                    cmds.rowLayout(self.ui, e=True, visible=False)
                return not file_found

            # Files
            else:
                # Check whether the files contain the filter string and (un)hide the UI accordingly.
                if filter_str.casefold() not in self.name.casefold():
                    self.filtered = True
                    cmds.rowLayout(self.ui, e=True, visible=False)
                    return True
                else:
                    self.filtered = False
                    cmds.rowLayout(self.ui, e=True, visible=not self.collapsed)
                    return False

        def add_filter_children(self):
            """
            Add the filtered files to the selection.
            """
            # Directories
            if len(self._children) > 0:
                for ch in self._children:
                    ch.add_filter_children()
            # Files
            else:
                if not self.filtered:
                    self.set_included(True)
                    self.__parent.child_include(True)

        def add_filter(self, filter_field: str, error_field: str):
            """
            Sets the filter and immediately adds the children to the field.

            :param filter_field: The field in which the user can enter their filter string.
            :param error_field: The error field to be shown if no files were found.
            """
            self.filter(filter_field, error_field)
            self.add_filter_children()

        def set_to_filter(self, filter_field: str, error_field: str):
            """
            Sets the selection equal to the filter.
            :param filter_field: The field in which the user can enter their filter string.
            :param error_field: The error field to be shown if no files were found.
            """
            self._children[0].include_children(False)
            self.add_filter(filter_field, error_field)

        def prune_fbx(self, state) -> bool:
            pruned = state
            if len(self._children) > 0:
                for ch in self._children:
                    pruned = ch.prune_fbx(state) and pruned
                if self.depth > 0:
                    cmds.checkBox(self.checkbox, e=True, en=not pruned)
                return pruned

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
            Get all the included leaf node roots of the FileTree.
            :return: An array containing all the roots of leaf nodes flagged as included.
            """
            if not self.included:
                return []

            tree = []
            if len(self._children) > 0:
                for ch in self._children:
                    tree += ch.print_children()
            else:
                tree.append(self.root)

            return tree

        # TODO: Necessary?
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
            tree.append(self.root)
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
        if cmds.window("AssetLibraryBatchProcessor", ex=True):
            cmds.setFocus(self._window)
            return
        # Create the window and set up the master layout.
        cmds.window("AssetLibraryBatchProcessor", t="Asset Library Batch Processor", widthHeight=(900, 535))
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

        # Set up the bottom buttons: Run and Cancel
        cmds.setParent(master_layout)
        cmds.separator(style="out")
        button_layout = cmds.formLayout()
        run_button = cmds.button(l="Run")
        cancel_button = cmds.button(l="Cancel", c=lambda _: self.cancel())
        cmds.formLayout(button_layout, e=True, attachForm=[(cancel_button, "right", 10)],
                        attachControl=[(run_button, "right", 10, cancel_button)])

    def __create_file_layout(self, main_layout: str):
        """
        Creates the File layout. This contains the source file system as well as the search.
        :param main_layout: The parent layout to which this layout should be parented.
        """
        # Create the File system lay-out
        file_layout = cmds.columnLayout(adj=True, rs=0, p=main_layout)
        cmds.frameLayout(label=f"SOURCE FILES", p=file_layout)

        # Setup of the Source selection
        target = cmds.formLayout(h=45)
        target_label = cmds.text(l="Source:", font="boldLabelFont", h=20)
        target_field = cmds.textField(h=20, ed=False, bgc=[0.2, 0.2, 0.2], w=300)
        target_browse = cmds.button(l="Browse", h=20)
        cmds.formLayout(target, e=True, attachForm=[(target_label, "left", 10), (target_browse, "right", 5),
                                                    (target_label, "top", 16), (target_field, "top", 16),
                                                    (target_browse, "top", 15)],
                        attachControl=[(target_field, "left", 15, target_label),
                                       (target_field, "right", 8, target_browse)])

        cmds.button(target_browse, e=True, c=lambda _: self.source_browse(target_field))

        cmds.separator(p=file_layout, h=15)

        # Setup of the File System Layout
        self.files_scroll = cmds.scrollLayout(w=350, h=300, cr=True, vsb=True, p=file_layout, bgc=[0.2, 0.2, 0.2])
        filter_error = cmds.text(l="No files containing the filter string were found.", visible=False)
        self.__files_layout = cmds.formLayout()
        self._update_all_files(self._root, target_field)

        cmds.separator(p=file_layout, h=15)

        # Setup of the Search bar
        search = cmds.formLayout(p=file_layout)
        search_label = cmds.text(l="Search files:", font="boldLabelFont", h=20)
        search_field = cmds.textField(h=20)
        cmds.textField(search_field, e=True, cc=lambda _: self._folder_structure.filter(search_field, filter_error))
        add_sel_filter_button = cmds.button(l="Add search to selection",
                                            c=lambda _: self._folder_structure.add_filter(search_field, filter_error))
        sel_filter_button = cmds.button(l="Set selection to search",
                                        c=lambda _: self._folder_structure.set_to_filter(search_field, filter_error))
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

    def __create_settings_layout(self, main_layout: str):
        """
        Creates the settings layout. Contains all settings pertaining to
        the actual processes when running over the batch.
        :param main_layout: The layout to which the settings layout should be parented.
        """
        # Main layout of the settings
        settings_layout = cmds.columnLayout(adj=True, p=main_layout)
        cmds.frameLayout(l="PROCESSES", w=350)

        # Setup of the picking of a Target directory.
        target = cmds.formLayout(h=50)
        target_label = cmds.text(l="Target:", font="boldLabelFont", h=20)
        target_field = cmds.textField(h=20, ed=False, bgc=[0.2, 0.2, 0.2])
        target_browse = cmds.button(l="Browse", h=20)
        cmds.formLayout(target, e=True, attachForm=[(target_label, "left", 10), (target_browse, "right", 5),
                                                    (target_label, "top", 16), (target_field, "top", 16),
                                                    (target_browse, "top", 15)],
                        attachControl=[(target_field, "left", 15, target_label),
                                       (target_field, "right", 8, target_browse)])

        # Setup of the export settings layout
        export_layout = cmds.frameLayout(l="Export Settings", cll=True, p=settings_layout, cl=True)
        self.create_export_frame(export_layout)

        cmds.button(target_browse, e=True, c=lambda _: self.target_browse(target_field))

        cmds.separator(p=settings_layout, h=25)

        # Setup of the process setting layouts.
        (pivot, pivot_frame) = self.create_process_container(settings_layout, "Pivot")
        pivot_inner = self.create_pivot_frame(pivot_frame)
        cmds.checkBox(pivot, e=True, cc=lambda state: self.set_pivot(state, pivot_inner))

        cmds.setParent(settings_layout)
        (scale, scale_frame) = self.create_process_container(settings_layout, "Scaling")
        scale_inner = self.create_scale_frame(scale_frame)
        cmds.checkBox(scale, e=True, cc=lambda state: self.set_scaling(state, scale_inner))

        return settings_layout

    @staticmethod
    def create_process_container(parent: str, label: str):
        """
        Creates a frame layout with a checkbox for process settings.
        :param parent: The parent of the new layout.
        :param label: The label displayed in the new frame layout.
        """
        form_layout = cmds.formLayout(p=parent)
        checkbox = cmds.checkBox(v=True, l="", w=30)
        frame_layout = cmds.frameLayout(l=label, cll=True)
        cmds.formLayout(form_layout, e=True, attachForm=[(checkbox, "left", 0), (frame_layout, "top", 0),
                                                         (checkbox, "top", 4), (frame_layout, "right", 0),
                                                         (frame_layout, "bottom", 8)],
                        attachControl=[(frame_layout, "left", 5, checkbox)])
        return checkbox, frame_layout

    def create_pivot_frame(self, frame: str):
        """
        Creates the layout for the pivot settings.
        :param frame: The parent frame layout.
        """
        pivot_master = cmds.columnLayout(p=frame, adj=True)

        cmds.text(l="Set the pivot location of the meshes relative to the object's \nbounding box:", align="left",
                  w=350)
        cmds.rowLayout(h=5, nc=1)
        cmds.setParent("..")

        options = ["Min", "Middle", "Max"]
        self.create_radio_group("X", pivot_master, options)
        self.create_radio_group("Y", pivot_master, options)
        self.create_radio_group("Z", pivot_master, options)
        cmds.rowLayout(h=5, p=pivot_master)

        return pivot_master

    @staticmethod
    def create_radio_group(label: str, layout: str, options: [str], default_opt: int = 1, label_width: int = 50,
                           align: str = "center", width: int = 80) -> str:
        """
        Creates a group of radio-like buttons with the given options.
        :param label: The label in front of the radio buttons.
        :param layout: The parent layout.
        :param options: The labels for the possible buttons.
        :param default_opt: The default selected index from 0 to len - 1.
        :param label_width: The width of the label.
        :param align: The alignment of the label.
        :param width: The buttons' width.
        :return: The name of the iconTextRadioCollection created.
        """
        cmds.rowLayout(nc=4, p=layout)
        cmds.text(l=label, w=label_width, h=20, align=align)

        radio_collection = cmds.iconTextRadioCollection()
        buttons = []
        for opt in options:
            button = cmds.iconTextRadioButton(st='textOnly', l=opt, w=width, bgc=[0.4, 0.4, 0.4], h=20)
            buttons.append(button)
        cmds.iconTextRadioCollection(radio_collection, e=True, select=buttons[default_opt])
        return radio_collection

    def create_scale_frame(self, frame: str):
        """
        Creates the layout for the scale settings.
        :param frame: The layout to parent the new layout to.
        """
        scale_master = cmds.columnLayout(p=frame, adj=True)
        cmds.text(l="Set the grid scale of the meshes. Meshes will be scaled up or \n"
                    "down towards the nearest grid point that is not zero:", align="left", w=350)
        button_width = 80

        checkbox_layout = cmds.formLayout(p=scale_master)
        scale_row = cmds.columnLayout(adj=True, p=checkbox_layout, visible=self.allow_stretching)
        cmds.rowLayout(nc=4)
        cmds.text(l="Scaling", w=50, h=20)
        scale_x = cmds.textField(w=button_width, text="50")
        scale_y = cmds.textField(w=button_width, text="50")
        scale_z = cmds.textField(w=button_width, text="50")
        self.scale_all = [scale_x, scale_y, scale_z]

        non_stretch = cmds.columnLayout(p=checkbox_layout, visible=not self.allow_stretching)
        self.create_radio_group("Main Axis", non_stretch, ["X", "Y", "Z"], 0, 60, "left", 70)
        cmds.rowLayout(nc=2, p=non_stretch)
        cmds.text(l="Scaling", w=58, h=22, align="left")
        self.scale = cmds.textField(w=75, text="50")

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
        fbx_only = cmds.checkBox(v=not self.fbx_only, l="Also copy non-fbx files", p=export_layout,
                                 cc=lambda state: self.set_prune_fbx(not state))
        self.set_prune_fbx(self.fbx_only)

        own_fbx = cmds.checkBox(v=self.own_fbx, l="Give each mesh its own fbx file", p=export_layout,
                                cc=lambda state: self.set_own_fbx(state), en=not self.combine_meshes)
        combine_meshes = cmds.checkBox(v=self.combine_meshes, l="Combine meshes", p=export_layout,
                                       cc=lambda state: self.set_combine(state, own_fbx))
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
        new_source_lst = cmds.fileDialog2(ds=1, fm=3, dir=self._root)
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
        new_dest_lst = cmds.fileDialog2(ds=1, fm=3, dir=self._dest)
        if new_dest_lst is not None:
            new_dest = new_dest_lst[0]
            no_error = self.check_dest(new_dest, lambda: self.target_browse(field))

            if no_error:
                self._dest = new_dest
                cmds.textField(field, e=True, text=new_dest)

    def set_stretching(self, state, ui_true, ui_false):
        self.allow_stretching = state
        cmds.columnLayout(ui_true, e=True, visible=state)
        cmds.columnLayout(ui_false, e=True, visible=not state)

    def set_prune_fbx(self, fbx_only: bool = True):
        self.fbx_only = fbx_only
        self._folder_structure.prune_fbx(fbx_only)

    def set_combine(self, state, own_fbx_layout):
        self.combine_meshes = state
        cmds.checkBox(own_fbx_layout, e=True, en=not state)

    def set_own_fbx(self, state):
        self.own_fbx = state

    def set_scaling(self, state, inner):
        self.scaling = state
        cmds.columnLayout(inner, e=True, en=state)

    def set_pivot(self, state, inner):
        self.pivot = state
        cmds.columnLayout(inner, e=True, en=state)

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
        if root is "":
            self.error_message(fn, "No target folder was set. Please select one.",
                               *args, **kwargs)
            return False
        path = os.path.join(root, "_output")
        if not os.access(root, os.W_OK):
            self.error_message(fn, "No permission to write in this folder. Please choose a different destination.",
                               *args, **kwargs)
            return False

        if os.path.exists(path):
            dialog = cmds.confirmDialog(message="There is already an output folder (/_output) at this destination. \n"
                                                "\nThis tool will overwrite any duplicate files. If this is not wanted,"
                                                "\n please choose a different directory.", button=["Retry", "Close"],
                                        title="WARNING", ma="left", icn="warning")
            if dialog == "Retry":
                fn(*args, **kwargs)
                return False
        return True

    # ################################################# #
    # ################### PROCESSES ################### #

    def run(self) -> None:
        """
        Run the BatchProcessor.
        """
        cmds.showWindow(self._window)

    def cancel(self) -> None:
        cmds.deleteUI(self._window)

    def _update_all_files(self, directory: str, source_field: str) -> None:
        """
        Updates all the files in the file system to have the given directory as root.
        :param directory: The new root of the file system.
        """
        self._root = directory
        cmds.deleteUI(self.__files_layout)
        self.__files_layout = cmds.formLayout(p=self.files_scroll)
        self._folder_structure = self.FileTree(self._root, 0, self.__files_layout)

        parent_folders = [self._folder_structure]
        last_ui = self._folder_structure.ui
        folder_amount = [1]

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
                child_tree = self.FileTree(f, depth + 1, self.__files_layout, False, new_folder)
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

        cmds.textField(source_field, e=True, text=self._root)

    def set_file_sys_frame(self, tree: FileTree, last_ui: str) -> None:
        """
        Adds the FileTree root node to the UI.
        :param tree: The FileTree of which the root needs to be added.
        :param last_ui: The node above this one in the window.
        """
        cmds.formLayout(self.__files_layout, e=True,
                        attachForm=[(tree.ui, 'left', tree.depth*20-15), (tree.ui, 'right', 10)],
                        attachControl=[(tree.ui, 'top', 0, last_ui)])

    def _run_processor(self) -> None:
        """
        Running the actual processing of the BatchProcessor.
        """
        # Only on selected files.
        files = self._folder_structure.get_all_included_files()

        # Do the processing thingies for every file.
        for f in files:
            self.__adjust_pivots(f)
            self.__adjust_dimensions(f)
            self.__write_file(f)

    def __adjust_pivots(self, file: str):
        if file[:-4] != ".fbx":
            return
        pass

    def __adjust_dimensions(self, file: str):
        pass

    def __write_file(self, file: str):
        if self.fbx_only and file[:4] != ".fbx":
            return


# ############################################ #
# ################### MAIN ################### #

processor = BatchProcessor()

# TODO: Preference file + only one window open at a time? -> Set close command window!
# cmds.optionVar(ex=self.OPTION_VAR_NAME):
