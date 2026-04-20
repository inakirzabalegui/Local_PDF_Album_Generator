/**
 * Internationalization (i18n) module for ES/EN language support.
 * Loads before all other scripts and provides t() for translations.
 */

let currentLanguage = localStorage.getItem('language') || 'es';

const TRANSLATIONS = {
  es: {
    // Header / Navigation
    'header.edition': '📖 Edición',
    'header.source': '📸 Fuente',
    'header.open_folder': '📁 Abrir carpeta',
    'header.page_indicator': 'Página',
    'header.dark_mode': 'Modo oscuro',
    'header.debug': 'Ver log de depuración',
    'header.undo': '↶ Deshacer',
    'header.save': '💾 Guardar',
    'header.exit': '✕ Salir',
    'header.language': 'ES/EN',

    // Album Edition Sidebar - Info Section
    'album.section_info': 'Info',
    'album.page_title': 'Título de Página',
    'album.page_title_placeholder': 'Título de la página',
    'album.update_title': '✏️ Actualizar Título',
    'album.layout_mode': 'Modo de Layout',
    'album.layout_mesa': 'Mesa de Luz',
    'album.layout_grid': 'Grid Compacto',
    'album.layout_hibrido': 'Híbrido',
    'album.apply_layout': '⚙️ Aplicar Modo',
    'album.photo_caption': 'Subtítulo de Foto',
    'album.photo_caption_placeholder': 'Escribe un subtítulo para la foto seleccionada',
    'album.update_caption': '✏️ Actualizar Subtítulo',

    // Album Edition Sidebar - Actions Section
    'album.section_actions': 'Acciones',
    'album.regenerate_preview': '🔄 Regenerar Vista Previa',
    'album.add_page': '+ Añadir Página Después',
    'album.delete_page': '🗑️ Borrar Página Completa',

    // Album Edition Sidebar - Photos Section
    'album.section_photos': 'Fotos',
    'album.delete_photo': '🗑️ Borrar Foto Seleccionada',

    // Album Edition - Info box
    'album.info_mode': 'Modo:',
    'album.info_photos': 'Fotos:',

    // Album Edition - Page navigator
    'album.navigator_title': 'Navegador de páginas',
    'album.navigator_label': 'Páginas',

    // Source Mode Sidebar - Info Section
    'source.section_info': 'Info',
    'source.event_name': 'Nombre de Evento',
    'source.event_name_placeholder': 'Nombre del evento',
    'source.rename_event': '✏️ Renombrar Evento',

    // Source Mode Sidebar - Actions Section
    'source.section_actions': 'Acciones',
    'source.regenerate_album': '🔄 Regenerar Álbum',
    'source.delete_event': '🗑️ Borrar Evento Completo',

    // Source Mode Sidebar - Photos Section
    'source.section_photos': 'Fotos del Evento',
    'source.delete_photo': '🗑️ Borrar Foto',

    // Source Mode - Info box
    'source.info_event': 'Evento:',
    'source.info_photos': 'Fotos:',

    // Source Mode - Event navigator
    'source.navigator_title': 'Navegador de carpetas de evento',
    'source.navigator_label': 'Eventos',

    // Image/iframe alt/title
    'image.source_preview': 'Vista previa de foto',
    'image.page_preview': 'Vista previa de página',

    // Page title
    'page.title': 'Álbum PDF - {{ album_title }}',
    'page.title_app': 'Álbum PDF - Aplicación Unificada',

    // Loading messages
    'loading.default': 'Procesando...',
    'loading.preview': 'Generando vista previa...',
    'loading.album': 'Regenerando álbum...',
    'loading.dialog': 'Abriendo diálogo...',
    'loading.init': 'Inicializando...',

    // Error messages - Album Edition
    'error.load_page': 'Error al cargar la página: ',
    'error.connection_load_page': 'Error de conexión al cargar la página',
    'error.reorder_photos': 'Error al reordenar fotos: ',
    'error.connection_reorder': 'Error de conexión al reordenar fotos',
    'error.delete_photo': 'Error al borrar foto: ',
    'error.connection_delete_photo': 'Error de conexión al borrar foto',
    'error.create_page': 'Error al crear página: ',
    'error.connection_create_page': 'Error de conexión al crear página',
    'error.delete_page': 'Error al borrar página: ',
    'error.connection_delete_page': 'Error de conexión al borrar página',
    'error.update_title': 'Error al actualizar título: ',
    'error.connection_update_title': 'Error de conexión al actualizar título',
    'error.update_layout': 'Error al actualizar modo de layout: ',
    'error.connection_update_layout': 'Error de conexión al actualizar modo de layout',
    'error.preview': 'Error al regenerar vista previa: ',
    'error.connection_preview': 'Error de conexión al regenerar vista previa',
    'error.update_caption': 'Error al actualizar subtítulo: ',
    'error.connection_update_caption': 'Error de conexión al actualizar subtítulo',
    'error.undo': 'Error al deshacer la acción',
    'error.save': 'Error al guardar: ',
    'error.connection_save': 'Error de conexión al guardar',

    // Error messages - Source Mode
    'error.load_folders': 'Error al cargar carpetas: ',
    'error.connection_load_folders': 'Error de conexión al cargar carpetas',
    'error.load_event': 'Error al cargar evento: ',
    'error.connection_load_event': 'Error de conexión al cargar evento',
    'error.delete_source_photo': 'Error al borrar foto: ',
    'error.connection_delete_source_photo': 'Error de conexión al borrar foto',
    'error.rename_event': 'Error al renombrar evento: ',
    'error.connection_rename_event': 'Error de conexión al renombrar evento',
    'error.delete_event': 'Error al borrar evento: ',
    'error.connection_delete_event': 'Error de conexión al borrar evento',
    'error.regenerate_album': 'Error al regenerar álbum: ',
    'error.connection_regenerate_album': 'Error de conexión al regenerar álbum',

    // Validation & confirmations
    'validation.title_empty': 'El título no puede estar vacío',
    'validation.event_name_empty': 'El nombre del evento no puede estar vacío',
    'validation.path_required': 'Por favor, introduce una ruta válida',

    'confirm.delete_photo': '¿Borrar la foto "{{ name }}"?',
    'confirm.add_page': '¿Crear una página vacía después de la página {{ num }}?\n\nLas fotos se podrán mover a ella desde el editor.',
    'confirm.delete_page': '¿Borrar completamente la página {{ num }}?\n\nEsta acción no se puede deshacer.',
    'confirm.delete_event': '¿Borrar completamente el evento "{{ name }}"?\n\nEsta acción no se puede deshacer.',
    'confirm.regenerate_album': '¿Regenerar el álbum?\n\nEsto borrará el álbum existente y lo reconstruirá desde cero.\nEsta acción no se puede deshacer.',
    'confirm.discard_changes': '¿Descartar los cambios pendientes y abrir una carpeta diferente?',

    // Success messages
    'success.title': 'Cambios guardados correctamente',
    'success.page_created': 'Página creada. Las páginas se renumerarán en el próximo render.',
    'success.page_deleted': 'Página borrada. Las páginas se renumerarán en el próximo render.',
    'success.event_renamed': 'Evento renombrado. Las fotos dentro también han sido renombradas.',
    'success.event_deleted': 'Evento borrado.',
    'success.album_regenerated': 'Álbum regenerado correctamente.',
    'success.no_more_pages': 'No quedan más páginas en el álbum.',
    'success.unsaved_changes': 'Hay {{ count }} cambio(s) pendiente(s).\n\nLos cambios ya están guardados automáticamente.\n¿Cerrar el editor?',
    'success.can_close': 'Puedes cerrar esta pestaña manualmente.',

    // Launcher page
    'launcher.title': 'Álbum PDF',
    'launcher.subtitle': 'Crea hermosos álbumes fotográficos en PDF desde tus carpetas de fotos',
    'launcher.open_folder': '📁 Abrir Carpeta',
    'launcher.last_folder': '⏱️ Abrir último',
    'launcher.drag_drop': 'O arrastra una carpeta aquí',
    'launcher.drag_drop_note': '(Nota: los navegadores no exponen la ruta completa por limitaciones de seguridad)',
    'launcher.manual_label': 'O pega la ruta manualmente:',
    'launcher.manual_placeholder': '/ruta/completa/a/carpeta\nEjemplo: /Users/usuario/Fotos/Vacaciones',
    'launcher.use_folder': 'Usar esta carpeta',
    'launcher.drag_not_allowed': 'Los navegadores no permiten arrastra de carpetas por razones de seguridad. Por favor, usa "Abrir Carpeta" o pega la ruta manualmente.',
    'launcher.dialog_cancelled': 'Diálogo cancelado',
    'launcher.init_error': 'Error durante la inicialización',
    'launcher.connection_error': 'Error de conexión: ',
  },

  en: {
    // Header / Navigation
    'header.edition': '📖 Edition',
    'header.source': '📸 Source',
    'header.open_folder': '📁 Open folder',
    'header.page_indicator': 'Page',
    'header.dark_mode': 'Dark mode',
    'header.debug': 'View debug log',
    'header.undo': '↶ Undo',
    'header.save': '💾 Save',
    'header.exit': '✕ Exit',
    'header.language': 'ES/EN',

    // Album Edition Sidebar - Info Section
    'album.section_info': 'Info',
    'album.page_title': 'Page Title',
    'album.page_title_placeholder': 'Page title',
    'album.update_title': '✏️ Update Title',
    'album.layout_mode': 'Layout Mode',
    'album.layout_mesa': 'Light Table',
    'album.layout_grid': 'Compact Grid',
    'album.layout_hibrido': 'Hybrid',
    'album.apply_layout': '⚙️ Apply Mode',
    'album.photo_caption': 'Photo Caption',
    'album.photo_caption_placeholder': 'Write a caption for the selected photo',
    'album.update_caption': '✏️ Update Caption',

    // Album Edition Sidebar - Actions Section
    'album.section_actions': 'Actions',
    'album.regenerate_preview': '🔄 Regenerate Preview',
    'album.add_page': '+ Add Page After',
    'album.delete_page': '🗑️ Delete Full Page',

    // Album Edition Sidebar - Photos Section
    'album.section_photos': 'Photos',
    'album.delete_photo': '🗑️ Delete Selected Photo',

    // Album Edition - Info box
    'album.info_mode': 'Mode:',
    'album.info_photos': 'Photos:',

    // Album Edition - Page navigator
    'album.navigator_title': 'Page navigator',
    'album.navigator_label': 'Pages',

    // Source Mode Sidebar - Info Section
    'source.section_info': 'Info',
    'source.event_name': 'Event Name',
    'source.event_name_placeholder': 'Event name',
    'source.rename_event': '✏️ Rename Event',

    // Source Mode Sidebar - Actions Section
    'source.section_actions': 'Actions',
    'source.regenerate_album': '🔄 Regenerate Album',
    'source.delete_event': '🗑️ Delete Full Event',

    // Source Mode Sidebar - Photos Section
    'source.section_photos': 'Event Photos',
    'source.delete_photo': '🗑️ Delete Photo',

    // Source Mode - Info box
    'source.info_event': 'Event:',
    'source.info_photos': 'Photos:',

    // Source Mode - Event navigator
    'source.navigator_title': 'Event folder navigator',
    'source.navigator_label': 'Events',

    // Image/iframe alt/title
    'image.source_preview': 'Photo preview',
    'image.page_preview': 'Page preview',

    // Page title
    'page.title': 'PDF Album - {{ album_title }}',
    'page.title_app': 'PDF Album - Unified App',

    // Loading messages
    'loading.default': 'Processing...',
    'loading.preview': 'Generating preview...',
    'loading.album': 'Regenerating album...',
    'loading.dialog': 'Opening dialog...',
    'loading.init': 'Initializing...',

    // Error messages - Album Edition
    'error.load_page': 'Error loading page: ',
    'error.connection_load_page': 'Connection error loading page',
    'error.reorder_photos': 'Error reordering photos: ',
    'error.connection_reorder': 'Connection error reordering photos',
    'error.delete_photo': 'Error deleting photo: ',
    'error.connection_delete_photo': 'Connection error deleting photo',
    'error.create_page': 'Error creating page: ',
    'error.connection_create_page': 'Connection error creating page',
    'error.delete_page': 'Error deleting page: ',
    'error.connection_delete_page': 'Connection error deleting page',
    'error.update_title': 'Error updating title: ',
    'error.connection_update_title': 'Connection error updating title',
    'error.update_layout': 'Error updating layout mode: ',
    'error.connection_update_layout': 'Connection error updating layout mode',
    'error.preview': 'Error regenerating preview: ',
    'error.connection_preview': 'Connection error regenerating preview',
    'error.update_caption': 'Error updating caption: ',
    'error.connection_update_caption': 'Connection error updating caption',
    'error.undo': 'Error undoing action',
    'error.save': 'Error saving: ',
    'error.connection_save': 'Connection error saving',

    // Error messages - Source Mode
    'error.load_folders': 'Error loading folders: ',
    'error.connection_load_folders': 'Connection error loading folders',
    'error.load_event': 'Error loading event: ',
    'error.connection_load_event': 'Connection error loading event',
    'error.delete_source_photo': 'Error deleting photo: ',
    'error.connection_delete_source_photo': 'Connection error deleting photo',
    'error.rename_event': 'Error renaming event: ',
    'error.connection_rename_event': 'Connection error renaming event',
    'error.delete_event': 'Error deleting event: ',
    'error.connection_delete_event': 'Connection error deleting event',
    'error.regenerate_album': 'Error regenerating album: ',
    'error.connection_regenerate_album': 'Connection error regenerating album',

    // Validation & confirmations
    'validation.title_empty': 'Title cannot be empty',
    'validation.event_name_empty': 'Event name cannot be empty',
    'validation.path_required': 'Please enter a valid path',

    'confirm.delete_photo': 'Delete photo "{{ name }}"?',
    'confirm.add_page': 'Create an empty page after page {{ num }}?\n\nPhotos can be moved to it from the editor.',
    'confirm.delete_page': 'Delete full page {{ num }}?\n\nThis action cannot be undone.',
    'confirm.delete_event': 'Delete full event "{{ name }}"?\n\nThis action cannot be undone.',
    'confirm.regenerate_album': 'Regenerate the album?\n\nThis will delete the existing album and rebuild it from scratch.\nThis action cannot be undone.',
    'confirm.discard_changes': 'Discard pending changes and open a different folder?',

    // Success messages
    'success.title': 'Changes saved successfully',
    'success.page_created': 'Page created. Pages will be renumbered on next render.',
    'success.page_deleted': 'Page deleted. Pages will be renumbered on next render.',
    'success.event_renamed': 'Event renamed. Photos inside have been renamed too.',
    'success.event_deleted': 'Event deleted.',
    'success.album_regenerated': 'Album regenerated successfully.',
    'success.no_more_pages': 'No more pages in the album.',
    'success.unsaved_changes': 'There are {{ count }} pending change(s).\n\nChanges are already saved automatically.\nClose the editor?',
    'success.can_close': 'You can close this tab manually.',

    // Launcher page
    'launcher.title': 'PDF Album',
    'launcher.subtitle': 'Create beautiful photo albums in PDF from your photo folders',
    'launcher.open_folder': '📁 Open Folder',
    'launcher.last_folder': '⏱️ Open last',
    'launcher.drag_drop': 'Or drag a folder here',
    'launcher.drag_drop_note': '(Note: browsers do not expose the full path due to security limitations)',
    'launcher.manual_label': 'Or paste the path manually:',
    'launcher.manual_placeholder': '/complete/path/to/folder\nExample: /Users/username/Photos/Vacation',
    'launcher.use_folder': 'Use this folder',
    'launcher.drag_not_allowed': 'Browsers do not allow folder dragging for security reasons. Please use "Open Folder" or paste the path manually.',
    'launcher.dialog_cancelled': 'Dialog cancelled',
    'launcher.init_error': 'Initialization error',
    'launcher.connection_error': 'Connection error: ',
  }
};

/**
 * Get translation for a key with optional placeholder substitution.
 * Placeholders: {{ name }}, {{ num }}, {{ count }}
 */
function t(key, substitutions = {}) {
  const lang = TRANSLATIONS[currentLanguage] || TRANSLATIONS.es;
  let text = lang[key] || key;

  // Replace placeholders
  Object.keys(substitutions).forEach(placeholder => {
    text = text.replace(`{{ ${placeholder} }}`, substitutions[placeholder]);
  });

  return text;
}

/**
 * Set the current language and update the page.
 */
function setLanguage(lang) {
  if (lang === 'es' || lang === 'en') {
    currentLanguage = lang;
    localStorage.setItem('language', lang);
    applyTranslations();
    updateLanguageButton();
  }
}

/**
 * Toggle between Spanish and English.
 */
function toggleLanguage() {
  setLanguage(currentLanguage === 'es' ? 'en' : 'es');
}

/**
 * Apply translations to all elements with i18n attributes.
 */
function applyTranslations() {
  // Translate text content
  document.querySelectorAll('[data-i18n]').forEach(el => {
    const key = el.getAttribute('data-i18n');
    el.textContent = t(key);
  });

  // Translate placeholders
  document.querySelectorAll('[data-i18n-placeholder]').forEach(el => {
    const key = el.getAttribute('data-i18n-placeholder');
    el.placeholder = t(key);
  });

  // Translate titles (tooltips)
  document.querySelectorAll('[data-i18n-title]').forEach(el => {
    const key = el.getAttribute('data-i18n-title');
    el.title = t(key);
  });
}

/**
 * Update the language button text to show current language.
 */
function updateLanguageButton() {
  const btn = document.getElementById('lang-btn');
  if (btn) {
    btn.textContent = currentLanguage.toUpperCase();
  }
}

// Initialize on page load
document.addEventListener('DOMContentLoaded', () => {
  applyTranslations();
  updateLanguageButton();
});
