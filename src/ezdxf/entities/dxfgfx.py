# Copyright (c) 2019-2020 Manfred Moitzi
# License: MIT License
# Created 2019-02-13
#
# DXFGraphic - graphical DXF entities stored in ENTITIES and BLOCKS sections
from typing import TYPE_CHECKING, Optional, Tuple, Iterable, Callable, Dict
import warnings
from ezdxf.lldxf.attributes import DXFAttr, DXFAttributes, DefSubclass
from ezdxf.lldxf.const import DXF12, DXF2000, DXF2004, DXF2007, DXF2013, DXFValueError, DXFKeyError, DXFTableEntryError
from ezdxf.lldxf.const import SUBCLASS_MARKER, DXFInvalidLayerName, DXFInvalidLineType
from ezdxf.lldxf.const import DXFStructureError
from ezdxf.lldxf.validator import is_valid_layer_name
from .dxfentity import DXFEntity, base_class, SubclassProcessor
from ezdxf.math import OCS, UCS, Matrix44
from ezdxf.tools.rgb import int2rgb, rgb2int
from ezdxf.tools import float2transparency, transparency2float
from .factory import register_entity
from ezdxf import options
from ezdxf.proxygraphic import load_proxy_graphic, export_proxy_graphic

if TYPE_CHECKING:
    from ezdxf.eztypes import Auditor, TagWriter, BaseLayout, DXFNamespace, Vertex, Drawing

__all__ = ['DXFGraphic', 'acdb_entity', 'entity_linker', 'SeqEnd', 'add_entity', 'replace_entity']

GRAPHIC_PROPERTIES = {'layer', 'linetype', 'color', 'lineweight', 'ltscale', 'true_color', 'color_name', }

acdb_entity = DefSubclass('AcDbEntity', {
    'layer': DXFAttr(8, default='0'),  # layername as string
    'linetype': DXFAttr(6, default='BYLAYER', optional=True),  # linetype as string, special names BYLAYER/BYBLOCK
    'color': DXFAttr(62, default=256, optional=True),  # dxf color index, 0 .. BYBLOCK, 256 .. BYLAYER
    'paperspace': DXFAttr(67, default=0, optional=True),  # 0 .. modelspace, 1 .. paperspace
    # thickness and extrusion is defined in Entity specific subclasses
    # Stored and moved around as a 16-bit integer
    'lineweight': DXFAttr(370, default=-1, dxfversion=DXF2000, optional=True),
    # Line weight in mm times 100 (e.g. 0.13mm = 13). Smallest line weight is 13 and biggest line weight is 200, values
    # outside this range prevents AutoCAD from loading the file.
    # Special values:
    # LINEWEIGHT_BYLAYER = -1
    # LINEWEIGHT_BYBLOCK = -2
    # LINEWEIGHT_DEFAULT = -3
    #
    'ltscale': DXFAttr(48, default=1.0, dxfversion=DXF2000, optional=True),  # linetype scale
    'invisible': DXFAttr(60, default=0, dxfversion=DXF2000, optional=True),  # invisible .. 1, visible .. 0
    'true_color': DXFAttr(420, dxfversion=DXF2004, optional=True),  # true color as 0x00RRGGBB 24-bit value
    'color_name': DXFAttr(430, dxfversion=DXF2004, optional=True),  # color name as string
    'transparency': DXFAttr(440, dxfversion=DXF2004, optional=True),
    # transparency value 0x020000TT 0 = fully transparent / 255 = opaque
    'shadow_mode': DXFAttr(284, dxfversion=DXF2007, optional=True),  # shadow_mode
    # 0 = Casts and receives shadows
    # 1 = Casts shadows
    # 2 = Receives shadows
    # 3 = Ignores shadows
    'material_handle': DXFAttr(347, dxfversion=DXF2007, optional=True),
    'visualstyle_handle': DXFAttr(348, dxfversion=DXF2007, optional=True),

    # objects may use the full range, but entity classes only use 381-389 DXF group codes in their representation, for
    # the same reason as the Lineweight range above

    # PlotStyleName type enum (AcDb::PlotStyleNameType). Stored and moved around as a 16-bit integer. Custom non-entity
    'plotstyle_enum': DXFAttr(380, dxfversion=DXF2007, default=1, optional=True),

    # Handle value of the PlotStyleName object, basically a hard pointer, but has a different range to make backward
    # compatibility easier to deal with.
    'plotstyle_handle': DXFAttr(390, dxfversion=DXF2007, optional=True),

    # 92 or 160?: Number of bytes in the proxy entity graphics represented in the subsequent 310 groups, which are binary
    # chunk records (optional)
    # 310: Proxy entity graphics data (multiple lines; 256 characters max. per line) (optional)
    # Compiled by TagCompiler() to a DXFBinaryTag() objects

})


class DXFGraphic(DXFEntity):
    """
    Common base class for all graphic entities, a subclass of :class:`~ezdxf.entities.dxfentity.DXFEntity`.

    This entities resides in entity spaces like modelspace, any paperspace or blocks.
    """
    DXFTYPE = 'DXFGFX'
    DEFAULT_ATTRIBS = {'layer': '0'}
    DXFATTRIBS = DXFAttributes(base_class, acdb_entity)  # DXF attribute definitions

    def load_dxf_attribs(self, processor: SubclassProcessor = None) -> 'DXFNamespace':
        """ Adds subclass processing for 'AcDbEntity', requires previous base class processing by parent class.
        (internal API)
        """
        dxf = super().load_dxf_attribs(processor)
        if processor is None:
            return dxf
        r12 = processor.r12
        # It is valid to mix up the base class with AcDbEntity class.
        processor.append_base_class_to_acdb_entity()

        # Load proxy graphic data if requested
        if options.load_proxy_graphics:
            # length tag has group code 92 until DXF R2010
            if processor.dxfversion and processor.dxfversion < DXF2013:
                code = 92
            else:
                code = 160
            self.proxy_graphic = load_proxy_graphic(
                processor.subclasses[0 if r12 else 1],
                length_code=code,
            )

        # Load common AcDbEntity attributes into dxf namespace
        tags = processor.load_dxfattribs_into_namespace(dxf, acdb_entity, index=1)
        if len(tags) and not r12:
            processor.log_unprocessed_tags(tags, subclass=acdb_entity.name)
        return dxf

    def post_new_hook(self):
        """ Post processing and integrity validation after entity creation (internal API) """
        dxf = self.dxf
        if not is_valid_layer_name(dxf.layer):
            raise DXFInvalidLayerName(dxf.layer)

        if self.doc and dxf.hasattr('linetype'):
            if dxf.linetype not in self.doc.linetypes:
                raise DXFInvalidLineType('Linetype "{}" not defined.'.format(dxf.linetype))

    @property
    def rgb(self) -> Optional[Tuple[int, int, int]]:
        """ Returns RGB true color as (r, g, b) tuple or None if true_color is not set. """
        if self.dxf.hasattr('true_color'):
            return int2rgb(self.dxf.get('true_color'))
        else:
            return None

    @rgb.setter
    def rgb(self, rgb: Tuple[int, int, int]) -> None:
        """ Set RGB true color as (r, g , b) tuple e.g. (12, 34, 56). """
        self.dxf.set('true_color', rgb2int(rgb))

    @property
    def transparency(self) -> float:
        """ Get transparency as float value between 0 and 1, 0 is opaque and 1 is 100% transparent (invisible). """
        if self.dxf.hasattr('transparency'):
            return transparency2float(self.dxf.get('transparency'))
        else:
            return 0.

    @transparency.setter
    def transparency(self, transparency: float) -> None:
        """ Set transparency as float value between 0 and 1, 0 is opaque and 1 is 100% transparent (invisible). """
        self.dxf.set('transparency', float2transparency(transparency))

    def graphic_properties(self) -> Dict:
        """ Returns the important common properties layer, color, linetype, lineweight, ltscale, true_color
        and color_name as `dxfattribs` dict.

        .. versionadded:: 0.12

        """
        attribs = dict()
        for key in GRAPHIC_PROPERTIES:
            if self.dxf.hasattr(key):
                attribs[key] = self.dxf.get(key)
        return attribs

    def ocs(self) -> Optional[OCS]:
        """
        Returns object coordinate system (:ref:`ocs`) for 2D entities like :class:`Text` or :class:`Circle`,
        returns ``None`` for entities without OCS support.

        """
        # extrusion is only defined for 2D entities like Text, Circle, ...
        if self.dxf.is_supported('extrusion'):
            extrusion = self.dxf.get('extrusion', default=(0, 0, 1))
            return OCS(extrusion)
        else:
            return None

    def set_owner(self, owner: str, paperspace: int = 0) -> None:
        """ Set owner attribute and paperspace flag. (internal API)"""
        self.dxf.owner = owner
        if paperspace:
            self.dxf.paperspace = paperspace
        else:
            self.dxf.discard('paperspace')
        for e in self.linked_entities():  # type: DXFGraphic
            e.set_owner(owner, paperspace)

    def linked_entities(self) -> Iterable['DXFEntity']:
        """ Yield linked entities: VERTEX or ATTRIB, different handling than attached entities. (internal API)"""
        return []

    def attached_entities(self) -> Iterable['DXFEntity']:
        """ Yield attached entities: MTEXT,  different handling than linked entities. (internal API)"""
        return []

    def link_entity(self, entity: 'DXFEntity') -> None:
        """ Store linked or attached entities. Same API for both types of appended data, because entities with linked
        entities (POLYLINE, INSERT) have no attached entities and vice versa.

        (internal API)
        """
        pass

    @property
    def zorder(self):
        """ Inverted priority order (lowest value first) """
        return -self.priority

    @zorder.setter
    def zorder(self, value):
        self.priority = -value

    def export_entity(self, tagwriter: 'TagWriter') -> None:
        """ Export entity specific data as DXF tags. (internal API)"""
        # base class (handle, appid, reactors, xdict, owner) export is done by parent class
        self.export_acdb_entity(tagwriter)
        # xdata and embedded objects  export is also done by parent

    def export_acdb_entity(self, tagwriter: 'TagWriter'):
        """ Export subclass 'AcDbEntity' as DXF tags. (internal API)"""
        # Full control over tag order and YES, sometimes order matters
        not_r12 = tagwriter.dxfversion > DXF12
        if not_r12:
            tagwriter.write_tag2(SUBCLASS_MARKER, acdb_entity.name)

        self.dxf.export_dxf_attribs(tagwriter, [
            'paperspace', 'layer', 'linetype', 'material_handle', 'color', 'lineweight', 'ltscale', 'true_color',
            'color_name', 'transparency', 'plotstyle_enum', 'plotstyle_handle', 'shadow_mode',
            'visualstyle_handle',
        ])

        if self.proxy_graphic and not_r12 and options.store_proxy_graphics:
            # length tag has group code 92 until DXF R2010
            export_proxy_graphic(self.proxy_graphic, tagwriter,
                                 length_code=(92 if tagwriter.dxfversion < DXF2013 else 160))

    def get_layout(self) -> Optional['BaseLayout']:
        """ Returns the owner layout or returns ``None`` if entity is not assigned to any layout. """
        if self.dxf.owner is None:  # unlinked entity
            return None
        try:
            return self.doc.layouts.get_layout_by_key(self.dxf.owner)
        except DXFKeyError:
            pass
        try:
            return self.doc.blocks.get_block_layout_by_handle(self.dxf.owner)
        except DXFTableEntryError:
            return None

    def unlink_from_layout(self) -> None:
        """
        Unlink entity from associated layout. Does nothing if entity is already unlinked.

        It is more efficient to call the :meth:`~ezdxf.layouts.BaseLayout.unlink_entity` method
        of the associated layout, especially if you have to unlink more than one entity.

        .. versionadded:: 0.13

        """
        if not self.is_alive:
            raise TypeError('Can not unlink destroyed entity.')

        if self.doc is None:
            # no doc -> no layout
            self.dxf.owner = None
            return

        layout = self.get_layout()
        if layout:
            layout.unlink_entity(self)

    def move_to_layout(self, layout: 'BaseLayout', source: 'BaseLayout' = None) -> None:
        """
        Move entity from model space or a paper space layout to another layout. For block layout as source, the
        block layout has to be specified. Moving between different DXF drawings is not supported.

        Args:
            layout: any layout (model space, paper space, block)
            source: provide source layout, faster for DXF R12, if entity is in a block layout

        Raises:
            DXFStructureError: for moving between different DXF drawings

        """
        if source is None:
            source = self.get_layout()
            if source is None:
                raise DXFValueError('Source layout for entity not found.')
        source.move_to_layout(self, layout)

    def copy_to_layout(self, layout: 'BaseLayout') -> 'DXFEntity':
        """
        Copy entity to another `layout`, returns new created entity as :class:`DXFEntity` object. Copying between
        different DXF drawings not supported.

        Args:
            layout: any layout (model space, paper space, block)

        Raises:
            DXFStructureError: for copying between different DXF drawings

        """
        if self.doc != layout.doc:
            raise DXFStructureError('Copying between different DXF drawings not supported.')
        new_entity = self.copy()
        self.entitydb.add(new_entity)
        layout.add_entity(new_entity)
        return new_entity

    def audit(self, auditor: 'Auditor') -> None:
        """ Validity check. (internal API) """
        assert self.doc is auditor.doc, 'Auditor for different DXF document.'
        super().audit(auditor)
        auditor.check_owner_exist(self)
        auditor.check_for_valid_layer_name(self)
        auditor.check_entity_linetype(self)
        auditor.check_entity_color_index(self)

    def transform_to_wcs(self, ucs: 'UCS') -> 'DXFGraphic':
        warnings.warn(
            'DXFGraphic.transform_to_wcs(ucs) is deprecated, use transform(ucs.matrix). (removed in v0.15)',
            DeprecationWarning
        )
        return self.transform(ucs.matrix)

    def transform(self, m: 'Matrix44') -> 'DXFGraphic':
        """ Inplace transformation interface, returns `self` (floating interface).

        Args:
             m: 4x4 transformation matrix (:class:`ezdxf.math.Matrix44`)

        .. versionadded:: 0.13

        """
        raise NotImplementedError()

    def translate(self, dx: float, dy: float, dz: float) -> 'DXFGraphic':
        """ Translate entity inplace about `dx` in x-axis, `dy` in y-axis and `dz` in z-axis,
        returns `self` (floating interface).

        Basic implementation uses the :meth:`transform` interface, subclasses may have faster implementations.

        .. versionadded:: 0.13

        """
        return self.transform(Matrix44.translate(dx, dy, dz))

    def scale(self, sx: float, sy: float, sz: float) -> 'DXFGraphic':
        """ Scale entity inplace about `dx` in x-axis, `dy` in y-axis and `dz` in z-axis,
        returns `self` (floating interface).

        .. versionadded:: 0.13

        """
        return self.transform(Matrix44.scale(sx, sy, sz))

    def scale_uniform(self, s: float) -> 'DXFGraphic':
        """ Scale entity inplace uniform about `s` in x-axis, y-axis and z-axis,
        returns `self` (floating interface).

        .. versionadded:: 0.13

        """
        return self.transform(Matrix44.scale(s))

    def rotate_axis(self, axis: 'Vertex', angle: float) -> 'DXFGraphic':
        """ Rotate entity inplace about vector `axis`, returns `self` (floating interface).

        Args:
            axis: rotation axis as tuple or :class:`Vector`
            angle: rotation angle in radians

        .. versionadded:: 0.13

        """
        return self.transform(Matrix44.axis_rotate(axis, angle))

    def rotate_x(self, angle: float) -> 'DXFGraphic':
        """ Rotate entity inplace about x-axis, returns `self` (floating interface).

        Args:
            angle: rotation angle in radians

        .. versionadded:: 0.13

        """
        return self.transform(Matrix44.x_rotate(angle))

    def rotate_y(self, angle: float) -> 'DXFGraphic':
        """ Rotate entity inplace about y-axis, returns `self` (floating interface).

        Args:
            angle: rotation angle in radians

        .. versionadded:: 0.13

        """
        return self.transform(Matrix44.y_rotate(angle))

    def rotate_z(self, angle: float) -> 'DXFGraphic':
        """ Rotate entity inplace about z-axis, returns `self` (floating interface).

        Args:
            angle: rotation angle in radians

        .. versionadded:: 0.13

        """
        return self.transform(Matrix44.z_rotate(angle))

    def has_hyperlink(self) -> bool:
        """ Returns ``True`` if entity has an attached hyperlink.

        .. versionadded:: 0.12

        """
        return bool(self.xdata) and ('PE_URL' in self.xdata)

    def set_hyperlink(self, link: str, description: str = None, location: str = None):
        """ Set hyperlink of an entity.

        .. versionadded:: 0.12

        """
        xdata = [(1001, 'PE_URL'), (1000, str(link))]
        if description:
            xdata.append((1002, '{'))
            xdata.append((1000, str(description)))
            if location:
                xdata.append((1000, str(location)))
            xdata.append((1002, '}'))

        self.discard_xdata('PE_URL')
        self.set_xdata('PE_URL', xdata)
        if self.doc and 'PE_URL' not in self.doc.appids:
            self.doc.appids.new('PE_URL')
        return self

    def get_hyperlink(self) -> Tuple[str, str, str]:
        """ Returns hyperlink, description and location.

        .. versionadded:: 0.12

        """
        link = ""
        description = ""
        location = ""
        if self.xdata and 'PE_URL' in self.xdata:
            xdata = [tag.value for tag in self.get_xdata('PE_URL') if tag.code == 1000]
            if len(xdata):
                link = xdata[0]
            if len(xdata) > 1:
                description = xdata[1]
            if len(xdata) > 2:
                location = xdata[2]
        return link, description, location

    def remove_dependencies(self, other: 'Drawing' = None) -> None:
        """
        Remove all dependencies from actual document.
        (internal API)

        """
        if not self.is_alive:
            return

        super().remove_dependencies(other)
        # The layer attribute is preserved because layer doesn't need a layer table entry, the layer attributes are
        # reset to default attributes like color is 7 and linetype is CONTINUOUS
        has_linetype = (bool(other) and self.dxf.linetype in other.linetypes)
        if not has_linetype:
            self.dxf.linetype = 'BYLAYER'
        self.dxf.discard('material_handle')
        self.dxf.discard('visualstyle_handle')
        self.dxf.discard('plotstyle_enum')
        self.dxf.discard('plotstyle_handle')


@register_entity
class SeqEnd(DXFGraphic):
    DXFTYPE = 'SEQEND'


LINKED_ENTITIES = {
    'INSERT': 'ATTRIB',
    'POLYLINE': 'VERTEX'
}


# This attached MTEXT is a limited MTEXT entity, starting with (0, 'MTEXT') therefore separated entity, but without the
# base class: no handle, no owner nor AppData, and a limited AcDbEntity subclass.
# Detect attached entities (more than MTEXT?) by required but missing handle and owner tags
# use DXFEntity.link_entity() for linking to preceding entity, INSERT & POLYLINE do not have attached entities, so reuse
# of API for ATTRIB & ATTDEF should be safe.


def entity_linker() -> Callable[[DXFEntity], bool]:
    main_entity = None  # type: Optional[DXFEntity]
    prev = None  # type: Optional[DXFEntity] # store preceding entity
    expected = ""

    def entity_linker_(entity: DXFEntity) -> bool:
        nonlocal main_entity, expected, prev
        dxftype = entity.dxftype()  # type: str
        are_linked_entities = False  # INSERT & POLYLINE are not linked entities, they are stored in the entity space
        if main_entity is not None:
            are_linked_entities = True  # VERTEX, ATTRIB & SEQEND are linked tags, they are NOT stored in the entity space
            if dxftype == 'SEQEND':
                main_entity.link_seqend(entity)
                main_entity = None
            # check for valid DXF structure just VERTEX follows POLYLINE and just ATTRIB follows INSERT
            elif dxftype == expected:
                main_entity.link_entity(entity)
            else:
                raise DXFStructureError("expected DXF entity {} or SEQEND".format(dxftype))
        # linked entities
        elif dxftype in LINKED_ENTITIES:  # only these two DXF types have this special linked structure
            if dxftype == 'INSERT' and not entity.dxf.get('attribs_follow', 0):
                # INSERT must not have following ATTRIBS, ATTRIB can be a stand alone entity:
                #   INSERT with no ATTRIBS, attribs_follow == 0
                #   ATTRIB as stand alone entity
                #   ....
                #   INSERT with ATTRIBS, attribs_follow == 1
                #   ATTRIB as connected entity
                #   SEQEND
                #
                # Therefore a ATTRIB following an INSERT doesn't mean that these entities are connected.
                pass
            else:
                main_entity = entity
                expected = LINKED_ENTITIES[dxftype]
        # attached entities
        elif (dxftype == 'MTEXT') and (entity.dxf.handle is None):  # attached MTEXT entity
            if prev:
                prev.link_entity(entity)
                are_linked_entities = True
            else:
                raise DXFStructureError("Attached MTEXT entity without a preceding entity.")
        prev = entity
        return are_linked_entities  # inform caller if `entity` is linked to a parent entity

    return entity_linker_


def add_entity(source: 'DXFGraphic', target: 'DXFGraphic') -> None:
    """ Add `target` entity to the entity database and to the same layout as the `source` entity.
    """
    assert target.dxf.handle is None
    source.entitydb.add(target)
    layout = source.get_layout()
    if layout is not None:
        layout.add_entity(target)


def replace_entity(source: 'DXFGraphic', target: 'DXFGraphic') -> None:
    """ Add `target` entity to the entity database and to the same layout
    as the `source` entity and replace the `source` entity by the
    `target` entity.

    """
    assert target.dxf.handle is None
    target.dxf.handle = source.dxf.handle
    layout = source.get_layout()
    entitydb = source.entitydb

    if layout is not None:
        # replace in layout and entity database
        layout.delete_entity(source)
    else:
        # replace just in entity database
        source.entitydb.delete_entity(source)

    entitydb.add(target)
    if layout is not None:
        layout.add_entity(target)
