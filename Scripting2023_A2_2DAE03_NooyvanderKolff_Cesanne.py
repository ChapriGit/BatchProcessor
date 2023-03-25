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

class BatchProcessor(object):
    __instance = None

    def __new__(cls):
        """
        Creates a BatchProcessor object if not yet created. Otherwise, returns the previous instance.
        """
        if not hasattr(cls, 'instance'):
            cls.__instance = object.__new__(cls)
            cls.__instance.__initialised = False
        return cls.__instance

    def __init__(self):
        if self.__initialised:
            cmds.setFocus(self._window)
            return
        self.__initialised = True

        # Start in current directory, have a button to change it
        self._root = r"C:\Users\cnvdk\DocumentsHowest\Scripting_2\TestProject\src"

        # TODO: FBX checkbox
        self.fbx_only = False

        # TODO: Log file
        self.log_file = ""
        self.__create_window()

    # ################################################################### #
    # ################## Helper Functions and Classes ################### #

    def __write_to_log(self, line: str):
        with open(self.log_file, "a") as f:
            f.write(line + "\n")

    # TODO: Lambdas
    @staticmethod
    def wrapper_function(fn, *args, **kwargs):
        """
        A function to wrap a function, discarding the first input. Parameters can be given along as well.
        :param fn: The function to be wrapped.
        :return: A wrapped function with the specified parameters.
        """
        def wrapped(_):
            fn(*args, **kwargs)
        return wrapped

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

            # If not the root, create the ui for it.
            if depth > 0:
                self.ui = self.__create_ui(folder, layout)
            else:
                self.ui = cmds.rowLayout()

        def __create_ui(self, folder: bool, parent) -> str:
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
                cmds.rowLayout(layout, e=True, h=20, bgc=[0.15, 0.15, 0.16])

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
                ch.__include_children(self.included)

            # Re-enable the parent if excluded.
            if self.depth > 1:
                self.__parent.child_include(self.included)

        def __include_children(self, state) -> None:
            """
            Sets the included value of the entire FileTree to the given state.
            :param state: Boolean to set the included to.
            """
            cmds.checkBox(self.checkbox, e=True, value=state)
            self.included = state

            if not self.included:
                cmds.text(self.label, e=True, font="boldLabelFont")
                self.bolded = True
            else:
                cmds.text(self.label, e=True, font="plainLabelFont")
                self.bolded = False

            # Also set the children
            for ch in self._children:
                ch.__include_children(self.included)

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
                self.included = state
                cmds.checkBox(self.checkbox, e=True, value=state)

                if self.depth > 1:
                    self.__parent.child_include(state)

            if not plain_font and self.depth > 1:
                if change_state and not state:
                    cmds.text(self.label, e=True, font="boldLabelFont")
                else:
                    cmds.text(self.label, e=True, font="obliqueLabelFont")
                self.bolded = True
            else:
                cmds.text(self.label, e=True, font="plainLabelFont")
                self.bolded = False

        # TODO Documentation
        def filter(self, filter_field: str, error_field: str):
            self.filtered = True
            filter_str = cmds.textField(filter_field, q=True, text=True)

            hidden = False
            for ch in self._children:
                hidden = ch.filter_str(filter_str)

            cmds.text(error_field, e=True, visible=hidden)

        def filter_str(self, filter_str: str):
            if len(self._children) > 0:
                hidden = []

                for ch in self._children:
                    hidden.append(ch.filter_str(filter_str))
                file_found = False in hidden
                self.filtered = not file_found
                if file_found:
                    cmds.rowLayout(self.ui, e=True, visible=not self.collapsed)
                else:
                    cmds.rowLayout(self.ui, e=True, visible=False)
                return not file_found

            else:
                if filter_str not in self.name:
                    self.filtered = True
                    cmds.rowLayout(self.ui, e=True, visible=False)
                    return True
                else:
                    self.filtered = False
                    cmds.rowLayout(self.ui, e=True, visible=not self.collapsed)
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
        Creates the BatchProcessor window.
        """
        # Create the window and set up the master layout.
        self._window = cmds.window("Asset Library Batch Processor", widthHeight=(800, 500))
        self.__master_layout = cmds.columnLayout(adj=True, rs=15)

        main_layout = cmds.formLayout()
        file_layout = self.__create_file_layout(main_layout)
        separator = cmds.separator(hr=False, style="out", p=main_layout)
        settings_layout = self.__create_settings_layout(main_layout)

        cmds.formLayout(main_layout, e=True,
                        attachForm=[(file_layout, "left", 10), (file_layout, "top", 10),
                                    (settings_layout, "right", 10), (settings_layout, "top", 10),
                                    (separator, "top", 10), (separator, "bottom", 10)],
                        attachControl=[(file_layout, "right", 15, separator),
                                       (separator, "right", 15, settings_layout)])

        cmds.setParent(self.__master_layout)
        cmds.separator(style="out")
        button_layout = cmds.formLayout()
        run_button = cmds.button(l="Run")
        cancel_button = cmds.button(l="Cancel")
        cmds.formLayout(button_layout, e=True, attachForm=[(cancel_button, "right", 10)],
                        attachControl=[(run_button, "right", 10, cancel_button)])

    def __create_file_layout(self, main_layout):
        # Create the File system lay-out
        file_layout = cmds.columnLayout(adj=True, rs=0, p=main_layout)

        cmds.frameLayout(label=f"SOURCE FILES", p=file_layout)

        target = cmds.formLayout(h=45)
        target_label = cmds.text(l="Source:", font="boldLabelFont", h=20)
        target_field = cmds.textField(h=20, ed=False, bgc=[0.2, 0.2, 0.2])
        target_browse = cmds.button(l="Browse", h=20)
        cmds.formLayout(target, e=True, attachForm=[(target_label, "left", 10), (target_browse, "right", 5),
                                                    (target_label, "top", 16), (target_field, "top", 16),
                                                    (target_browse, "top", 15)],
                        attachControl=[(target_field, "left", 15, target_label),
                                       (target_field, "right", 8, target_browse)])

        cmds.separator(p=file_layout, h=15)

        cmds.scrollLayout(w=350, h=300, cr=True, vsb=True, p=file_layout)
        filter_error = cmds.text(l="No files containing the filter string were found.", visible=False)
        self.__files_layout = cmds.formLayout()
        self._update_all_files(self._root)

        cmds.separator(p=file_layout, h=15)

        search = cmds.formLayout(h=40, p=file_layout)
        search_label = cmds.text(l="Search files:", font="boldLabelFont", h=20)
        search_field = cmds.textField(h=20)
        # TODO: Optional or maybe a button instead?
        # self.filter_only = cmds.checkBox(v=False, l="Only use filtered files")
        self.fbx_only = cmds.checkBox(v=False, l="Ignore non-fbx files")
        cmds.textField(search_field, e=True, cc=lambda _: self._folder_structure.filter(search_field, filter_error))
        cmds.formLayout(search, e=True, attachForm=[(search_label, "left", 10), (search_field, "right", 5),
                                                    (search_label, "top", 0), (search_field, "top", 0),
                                                    (self.fbx_only, "left", 10)],
                        attachControl=[(search_field, "left", 15, search_label),
                                       (self.fbx_only, "top", 5, search_label)])

        return file_layout

    def __create_settings_layout(self, main_layout):
        settings_layout = cmds.columnLayout(adj=True, p=main_layout)
        cmds.frameLayout(l="PROCESSES", w=400)

        target = cmds.formLayout(h=50)
        target_label = cmds.text(l="Target:", font="boldLabelFont", h=20)
        target_field = cmds.textField(h=20, ed=False, bgc=[0.2, 0.2, 0.2])
        target_browse = cmds.button(l="Browse", h=20)
        cmds.formLayout(target, e=True, attachForm=[(target_label, "left", 10), (target_browse, "right", 5),
                                                    (target_label, "top", 16), (target_field, "top", 16),
                                                    (target_browse, "top", 15)],
                        attachControl=[(target_field, "left", 15, target_label),
                                       (target_field, "right", 8, target_browse)])

        (self.pivot, pivot_frame) = self.create_process_container(settings_layout, "Pivot")
        self.create_pivot_frame(pivot_frame)

        (self.scale, scale_frame) = self.create_process_container(settings_layout, "Scaling")
        self.create_scale_frame(scale_frame)

        return settings_layout

    @staticmethod
    def create_process_container(parent, label):
        form_layout = cmds.formLayout(p=parent)
        checkbox = cmds.checkBox(v=True, l="", w=30)
        frame_layout = cmds.frameLayout(l=label, cll=True)
        cmds.formLayout(form_layout, e=True, attachForm=[(checkbox, "left", 0), (frame_layout, "top", 0),
                                                         (checkbox, "top", 4), (frame_layout, "right", 0),
                                                         (frame_layout, "bottom", 8)],
                        attachControl=[(frame_layout, "left", 5, checkbox)])
        return checkbox, frame_layout

    def create_pivot_frame(self, frame):
        pass

    def create_scale_frame(self, frame):
        pass

    # ################################################# #
    # ################### PROCESSES ################### #

    def run(self) -> None:
        """
        Run the BatchProcessor.
        """
        cmds.showWindow(self._window)

    def cancel(self) -> None:
        # TODO: Canceling
        pass

    def _update_all_files(self, directory: str) -> None:
        """
        Updates all the files in the file system to have the given directory as root.
        :param directory: The new root of the file system.
        """
        self._folder_structure = self.FileTree(self._root, 0, self.__files_layout)

        parent_folders = [self._folder_structure]
        last_ui = self._folder_structure.ui
        folder_amount = [1]

        file_iterator = os.walk(directory)
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

    def set_file_sys_frame(self, tree: FileTree, last_ui: str) -> None:
        """
        Adds the FileTree root node to the UI.
        :param tree: The FileTree of which the root needs to be added.
        :param last_ui: The node above this one in the window.
        """
        cmds.formLayout(self.__files_layout, e=True,
                        attachForm=[(tree.ui, 'left', tree.depth*20-15), (tree.ui, 'right', 10)],
                        attachControl=[(tree.ui, 'top', 0, last_ui)])

    def set_prune_fbx(self, fbx_only: bool = True):
        # TODO
        pass

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
processor.run()
