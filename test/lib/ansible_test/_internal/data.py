"""Context information for the current invocation of ansible-test."""
from __future__ import (absolute_import, division, print_function)
__metaclass__ = type

import os

from . import types as t

from .util import (
    ApplicationError,
    import_plugins,
    ANSIBLE_ROOT,
    is_subdir,
    ANSIBLE_IS_INSTALLED,
    ANSIBLE_LIB_ROOT,
    ANSIBLE_TEST_ROOT,
)

from .provider import (
    find_path_provider,
    get_path_provider_classes,
    ProviderNotFoundForPath,
)

from .provider.source import (
    SourceProvider,
)

from .provider.source.unversioned import (
    UnversionedSource,
)

from .provider.source.installed import (
    InstalledSource,
)

from .provider.layout import (
    ContentLayout,
    LayoutProvider,
)


class UnexpectedSourceRoot(ApplicationError):
    """Exception generated when a source root is found below a layout root."""
    def __init__(self, source_root, layout_root):  # type: (str, str) -> None
        super(UnexpectedSourceRoot, self).__init__('Source root "%s" cannot be below layout root "%s".' % (source_root, layout_root))

        self.source_root = source_root
        self.layout_root = layout_root


class DataContext:
    """Data context providing details about the current execution environment for ansible-test."""
    def __init__(self):
        content_path = os.environ.get('ANSIBLE_TEST_CONTENT_ROOT')
        current_path = os.getcwd()

        layout_providers = get_path_provider_classes(LayoutProvider)
        source_providers = get_path_provider_classes(SourceProvider)

        self.__source_providers = source_providers
        self.__ansible_source = None  # type: t.Optional[t.Tuple[t.Tuple[str, str], ...]]

        self.payload_callbacks = []  # type: t.List[t.Callable[t.List[t.Tuple[str, str]], None]]

        if content_path:
            content = self.__create_content_layout(layout_providers, source_providers, content_path, False)
        elif is_subdir(current_path, ANSIBLE_ROOT):
            content = self.__create_content_layout(layout_providers, source_providers, ANSIBLE_ROOT, False)
        else:
            content = self.__create_content_layout(layout_providers, source_providers, current_path, True)

        self.content = content  # type: ContentLayout

    @staticmethod
    def __create_content_layout(layout_providers,  # type: t.List[t.Type[LayoutProvider]]
                                source_providers,  # type: t.List[t.Type[SourceProvider]]
                                root,  # type: str
                                walk,  # type: bool
                                ):  # type: (...) -> ContentLayout
        """Create a content layout using the given providers and root path."""
        layout_provider = find_path_provider(LayoutProvider, layout_providers, root, walk)

        try:
            source_provider = find_path_provider(SourceProvider, source_providers, root, walk)
        except ProviderNotFoundForPath:
            source_provider = UnversionedSource(layout_provider.root)

        if source_provider.root != layout_provider.root and is_subdir(source_provider.root, layout_provider.root):
            raise UnexpectedSourceRoot(source_provider.root, layout_provider.root)

        layout = layout_provider.create(layout_provider.root, source_provider.get_paths(layout_provider.root))

        return layout

    def __create_ansible_source(self):
        """Return a tuple of Ansible source files with both absolute and relative paths."""
        if ANSIBLE_IS_INSTALLED:
            sources = []

            source_provider = InstalledSource(ANSIBLE_LIB_ROOT)
            sources.extend((os.path.join(source_provider.root, path), os.path.join('lib', 'ansible', path))
                           for path in source_provider.get_paths(source_provider.root))

            source_provider = InstalledSource(ANSIBLE_TEST_ROOT)
            sources.extend((os.path.join(source_provider.root, path), os.path.join('test', 'lib', 'ansible_test', path))
                           for path in source_provider.get_paths(source_provider.root))

            return tuple(sources)

        if self.content.is_ansible:
            return tuple((os.path.join(self.content.root, path), path) for path in self.content.all_files())

        try:
            source_provider = find_path_provider(SourceProvider, self.__source_providers, ANSIBLE_ROOT, False)
        except ProviderNotFoundForPath:
            source_provider = UnversionedSource(ANSIBLE_ROOT)

        return tuple((os.path.join(source_provider.root, path), path) for path in source_provider.get_paths(source_provider.root))

    @property
    def ansible_source(self):  # type: () -> t.Tuple[t.Tuple[str, str], ...]
        """Return a tuple of Ansible source files with both absolute and relative paths."""
        if not self.__ansible_source:
            self.__ansible_source = self.__create_ansible_source()

        return self.__ansible_source

    def register_payload_callback(self, callback):  # type: (t.Callable[t.List[t.Tuple[str, str]], None]) -> None
        """Register the given payload callback."""
        self.payload_callbacks.append(callback)


def data_init():  # type: () -> DataContext
    """Initialize provider plugins."""
    provider_types = (
        'layout',
        'source',
    )

    for provider_type in provider_types:
        import_plugins('provider/%s' % provider_type)

    try:
        context = DataContext()
    except ProviderNotFoundForPath:
        options = [
            ' - an Ansible collection: {...}/ansible_collections/{namespace}/{collection}/',
        ]

        if not ANSIBLE_IS_INSTALLED:
            options.insert(0, ' - the Ansible source: %s/' % ANSIBLE_ROOT)

        raise ApplicationError('''The current working directory must be at or below:

%s

Current working directory: %s''' % ('\n'.join(options), os.getcwd()))

    return context


def data_context():  # type: () -> DataContext
    """Return the current data context."""
    try:
        return data_context.instance
    except AttributeError:
        data_context.instance = data_init()
        return data_context.instance
