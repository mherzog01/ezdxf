# Created: 17.02.2019
# Copyright (c) 2019, Manfred Moitzi
# License: MIT License
from typing import TYPE_CHECKING, Optional
import logging
from ezdxf.lldxf.attributes import DXFAttr, DXFAttributes, DefSubclass, XType, VIRTUAL_TAG
from ezdxf.lldxf.const import DXF12, SUBCLASS_MARKER, DXFKeyError, LINEWEIGHT_BYBLOCK, DXF2007, DXF2000
from ezdxf.entities.dxfentity import SubclassProcessor, DXFEntity
from ezdxf.entities.layer import acdb_symbol_table_record
from .factory import register_entity
from ezdxf.render.arrows import ARROWS

logger = logging.getLogger('ezdxf')

if TYPE_CHECKING:
    from ezdxf.eztypes import TagWriter
    from ezdxf.drawing2 import Drawing
    from ezdxf.entities.dxfentity import DXFNamespace

__all__ = ['DimStyle']

base_class = DefSubclass(None, {
    'handle': DXFAttr(105),
    'owner': DXFAttr(330),
})

acdb_dimstyle = DefSubclass('AcDbDimStyleTableRecord', {
    'name': DXFAttr(2, default='Standard'),
    'flags': DXFAttr(70, default=0),
    'dimpost': DXFAttr(3, default=''),
    'dimapost': DXFAttr(4, default=''),
    # redirect dimblk/dimblk1/dimblk2 -> dimblk_handle/dimblk1_handle/dimblk2_handle
    'dimblk': DXFAttr(5, xtype=XType.callback, getter='get_dimblk', setter='set_dimblk', default=''),
    'dimblk1': DXFAttr(6, xtype=XType.callback, getter='get_dimblk1', setter='set_dimblk1', default=''),
    'dimblk2': DXFAttr(7, xtype=XType.callback, getter='get_dimblk2', setter='set_dimblk2', default=''),
    'dimscale': DXFAttr(40, default=1),
    'dimasz': DXFAttr(41, default=2.5),
    'dimexo': DXFAttr(42, default=0.625),
    'dimdli': DXFAttr(43, default=3.75),
    'dimexe': DXFAttr(44, default=1.25),
    'dimrnd': DXFAttr(45, default=0),
    'dimdle': DXFAttr(46, default=0),
    'dimtp': DXFAttr(47, default=0),
    'dimtm': DXFAttr(48, default=0),
    'dimfxl': DXFAttr(49, dxfversion=DXF2007, default=2.5),  # undocumented: length of extension line if fixed (dimfxlon = 1)
    'dimtxt': DXFAttr(140, default=2.5),
    'dimcen': DXFAttr(141, default=2.5),
    'dimtsz': DXFAttr(142, default=0),
    'dimaltf': DXFAttr(143, default=0.03937007874),
    'dimlfac': DXFAttr(144, default=1),
    'dimtvp': DXFAttr(145, default=0),
    'dimtfac': DXFAttr(146, dxfversion=DXF2000, default=1),
    'dimgap': DXFAttr(147, default=.625),
    'dimaltrnd': DXFAttr(148, dxfversion=DXF2000, default=0),
    'dimtfill': DXFAttr(69, dxfversion=DXF2007, default=0),  # 0=None, 1=canvas color, 2=dimtfillclr
    'dimtfillclr': DXFAttr(70, dxfversion=DXF2007, default=0),  # color index for dimtfill==2
    'dimtol': DXFAttr(71, default=0),
    'dimlim': DXFAttr(72, default=0),
    'dimtih': DXFAttr(73, default=0),
    'dimtoh': DXFAttr(74, default=0),
    'dimse1': DXFAttr(75, default=0),
    'dimse2': DXFAttr(76, default=0),
    'dimtad': DXFAttr(77, default=1),
    'dimzin': DXFAttr(78, default=8),
    'dimazin': DXFAttr(79, default=8, dxfversion=DXF2000),
    'dimalt': DXFAttr(170, default=0),
    'dimaltd': DXFAttr(171, default=3),
    'dimtofl': DXFAttr(172, default=1),
    'dimsah': DXFAttr(173, default=0),
    'dimtix': DXFAttr(174, default=0),
    'dimsoxd': DXFAttr(175, default=0),
    'dimclrd': DXFAttr(176, default=0),
    'dimclre': DXFAttr(177, default=0),
    'dimclrt': DXFAttr(178, default=0),
    'dimadec': DXFAttr(179, dxfversion=DXF2000, default=0),
    'dimunit': DXFAttr(270),  # obsolete
    'dimdec': DXFAttr(271, dxfversion=DXF2000, default=0),
    'dimtdec': DXFAttr(272, dxfversion=DXF2000, default=2),
    'dimaltu': DXFAttr(273, dxfversion=DXF2000, default=2),
    'dimalttd': DXFAttr(274, dxfversion=DXF2000, default=3),
    'dimaunit': DXFAttr(275, dxfversion=DXF2000, default=0),
    'dimfrac': DXFAttr(276, dxfversion=DXF2000, default=0),
    'dimlunit': DXFAttr(277, dxfversion=DXF2000, default=2),
    'dimdsep': DXFAttr(278, dxfversion=DXF2000, default=44),
    'dimtmove': DXFAttr(279, dxfversion=DXF2000, default=0),
    'dimjust': DXFAttr(280, dxfversion=DXF2000, default=0),
    'dimsd1': DXFAttr(281, dxfversion=DXF2000, default=0),
    'dimsd2': DXFAttr(282, dxfversion=DXF2000, default=0),
    'dimtolj': DXFAttr(283, dxfversion=DXF2000, default=0),
    'dimtzin': DXFAttr(284, dxfversion=DXF2000, default=8),
    'dimaltz': DXFAttr(285, dxfversion=DXF2000, default=0),
    'dimalttz': DXFAttr(286, dxfversion=DXF2000, default=0),
    'dimfit': DXFAttr(287),  # obsolete, now use DIMATFIT and DIMTMOVE
    'dimupt': DXFAttr(288, dxfversion=DXF2000, default=0),
    'dimatfit': DXFAttr(289, dxfversion=DXF2000, default=3),
    'dimfxlon': DXFAttr(290, dxfversion=DXF2007, default=0),  # undocumented: 1 = fixed extension line length
    'dimtxsty_handle': DXFAttr(340, dxfversion=DXF2000),  # handle of referenced STYLE entry
    # virtual DXF attribute 'dimtxsty': set/get referenced STYLE by name as callback
    'dimtxsty': DXFAttr(VIRTUAL_TAG, xtype=XType.callback, getter='get_text_style', setter='set_text_style'),
    # virtual DXF attribute 'dimldrblk': set/get referenced STYLE by name as callback
    'dimldrblk': DXFAttr(VIRTUAL_TAG, xtype=XType.callback, getter='get_dimldrblk', setter='set_dimldrblk'),
    'dimldrblk_handle': DXFAttr(341, dxfversion=DXF2000),  # handle of referenced BLOCK_RECORD
    'dimblk_handle': DXFAttr(342, dxfversion=DXF2000),  # handle of referenced BLOCK_RECORD
    'dimblk1_handle': DXFAttr(343, dxfversion=DXF2000),  # handle of referenced BLOCK_RECORD
    'dimblk2_handle': DXFAttr(344, dxfversion=DXF2000),  # handle of referenced BLOCK_RECORD

    'dimltype_handle': DXFAttr(345, dxfversion=DXF2007),  # handle of linetype for dimension line
    # virtual DXF attribute 'dimldtype': set/get referenced LINETYPE by name as callback
    'dimltype': DXFAttr(VIRTUAL_TAG,
                        xtype=XType.callback,
                        getter='get_linetype',
                        setter='set_linetype',
                        dxfversion=DXF2007),

    'dimltex1_handle': DXFAttr(346, dxfversion=DXF2007),  # handle of linetype for extension line 1
    # virtual DXF attribute 'dimltex1': set/get referenced LINETYPE by name as callback
    'dimltex1': DXFAttr(VIRTUAL_TAG,
                        xtype=XType.callback,
                        getter='get_ext1_linetype',
                        setter='set_ext1_linetype',
                        dxfversion=DXF2007),

    'dimltex2_handle': DXFAttr(347, dxfversion=DXF2007),  # handle of linetype for extension line 2
    # virtual DXF attribute 'dimltex2': set/get referenced LINETYPE by name as callback
    'dimltex2': DXFAttr(VIRTUAL_TAG,
                        xtype=XType.callback,
                        getter='get_ext2_linetype',
                        setter='set_ext2_linetype',
                        dxfversion=DXF2007),

    'dimlwd': DXFAttr(371, default=LINEWEIGHT_BYBLOCK, dxfversion=DXF2000),  # dimension line lineweight enum value, default BYBLOCK
    'dimlwe': DXFAttr(372, default=LINEWEIGHT_BYBLOCK, dxfversion=DXF2000),  # extension line lineweight enum value, default BYBLOCK
})

EXPORT_MAP_R2007 = [
    'name', 'flags', 'dimscale', 'dimasz', 'dimexo', 'dimdli', 'dimexe', 'dimrnd', 'dimdle', 'dimtp', 'dimtm', 'dimfxl',
    'dimtxt', 'dimcen', 'dimtsz', 'dimaltf', 'dimlfac', 'dimtvp', 'dimtfac', 'dimgap', 'dimaltrnd', 'dimtfill',
    'dimtfillclr', 'dimtol', 'dimlim', 'dimtih', 'dimtoh', 'dimse1', 'dimse2', 'dimtad', 'dimzin', 'dimazin', 'dimalt',
    'dimaltd', 'dimtofl', 'dimsah', 'dimtix', 'dimsoxd', 'dimclrd', 'dimclre', 'dimclrt', 'dimadec', 'dimdec',
    'dimtdec', 'dimaltu', 'dimalttd', 'dimaunit', 'dimfrac', 'dimlunit', 'dimdsep', 'dimtmove', 'dimjust', 'dimsd1',
    'dimsd2', 'dimtolj', 'dimtzin', 'dimaltz', 'dimalttz', 'dimupt', 'dimatfit', 'dimfxlon', 'dimtxsty_handle',
    'dimldrblk_handle', 'dimblk_handle', 'dimblk1_handle', 'dimblk2_handle', 'dimltype_handle',
    'dimltex1_handle', 'dimltex2_handle', 'dimlwd', 'dimlwe'
]

EXPORT_MAP_R2000 = [
    'name', 'flags', 'dimpost', 'dimapost', 'dimscale', 'dimasz', 'dimexo', 'dimdli', 'dimexe', 'dimrnd', 'dimdle',
    'dimtp', 'dimtm', 'dimtxt', 'dimcen', 'dimtsz', 'dimaltf', 'dimlfac', 'dimtvp', 'dimtfac', 'dimgap', 'dimaltrnd',
    'dimtol', 'dimlim', 'dimtih', 'dimtoh', 'dimse1', 'dimse2', 'dimtad', 'dimzin', 'dimazin', 'dimalt', 'dimaltd',
    'dimtofl', 'dimsah', 'dimtix', 'dimsoxd', 'dimclrd', 'dimclre', 'dimclrt', 'dimadec', 'dimdec', 'dimtdec',
    'dimaltu', 'dimalttd', 'dimaunit', 'dimfrac', 'dimlunit', 'dimdsep', 'dimtmove', 'dimjust', 'dimsd1', 'dimsd2',
    'dimtolj', 'dimtzin', 'dimaltz', 'dimalttz', 'dimupt', 'dimatfit', 'dimtxsty_handle', 'dimldrblk_handle',
    'dimblk_handle', 'dimblk1_handle', 'dimblk2_handle', 'dimlwd', 'dimlwe'
]

EXPORT_MAP_R12 = [
    'name', 'flags', 'dimpost', 'dimapost', 'dimblk', 'dimblk1', 'dimblk2', 'dimscale', 'dimasz', 'dimexo', 'dimdli',
    'dimexe', 'dimrnd', 'dimdle', 'dimtp', 'dimtm', 'dimtxt', 'dimcen', 'dimtsz', 'dimaltf', 'dimlfac', 'dimtvp',
    'dimtfac', 'dimgap', 'dimtol', 'dimlim', 'dimtih', 'dimtoh', 'dimse1', 'dimse2', 'dimtad', 'dimzin', 'dimalt',
    'dimaltd', 'dimtofl', 'dimsah', 'dimtix', 'dimsoxd', 'dimclrd', 'dimclre', 'dimclrt'
]


def dim_filter(name: str) -> bool:
    return name.startswith('dim')


@register_entity
class DimStyle(DXFEntity):
    """ DXF BLOCK_RECORD table entity """
    DXFTYPE = 'DIMSTYLE'
    DXFATTRIBS = DXFAttributes(base_class, acdb_symbol_table_record, acdb_dimstyle)
    CODE_TO_DXF_ATTRIB = dict(DXFATTRIBS.build_group_code_items(dim_filter))

    def load_dxf_attribs(self, processor: SubclassProcessor = None) -> 'DXFNamespace':
        dxf = super().load_dxf_attribs(processor)
        if processor is None:
            return dxf

        tags = processor.load_dxfattribs_into_namespace(dxf, acdb_dimstyle)
        if len(tags) and not processor.r12:
            processor.log_unprocessed_tags(tags, subclass=acdb_dimstyle.name)
        return dxf

    def export_entity(self, tagwriter: 'TagWriter') -> None:
        super().export_entity(tagwriter)
        # AcDbEntity export is done by parent class
        if tagwriter.dxfversion > DXF12:
            tagwriter.write_tag2(SUBCLASS_MARKER, acdb_symbol_table_record.name)
            tagwriter.write_tag2(SUBCLASS_MARKER, acdb_dimstyle.name)

        if tagwriter.dxfversion > DXF12:
            # set required values
            if not self.dxf.hasattr('dimtxsty_handle'):
                self.dxf.dimtxsty_handle = self.doc.styles.get('Standard').dxf.handle

        # for all DXF versions
        if tagwriter.dxfversion == DXF12:
            attribs = EXPORT_MAP_R12
        elif tagwriter.dxfversion < DXF2007:
            attribs = EXPORT_MAP_R2000
        else:
            attribs = EXPORT_MAP_R2007
        self.dxf.export_dxf_attribs(tagwriter, attribs, force=True)

    def _set_blk_handle(self, attr: str, arrow_name: str) -> None:
        if arrow_name == ARROWS.closed_filled:
            # special arrow, no handle needed (is '0' if set)
            # do not create block by default, this will be done if arrow is used
            # and block record handle is not needed here
            self.del_dxf_attrib(attr)
            return

        blocks = self.doc.blocks
        if ARROWS.is_acad_arrow(arrow_name):
            # create block, because need block record handle is needed here
            block_name = ARROWS.create_block(blocks, arrow_name)
        else:
            block_name = arrow_name

        blk = blocks.get(block_name)
        self.set_dxf_attrib(attr, blk.block_record_handle)

    def _get_arrow_block_name(self, name: str) -> str:
        handle = self.get_dxf_attrib(name, None)
        if handle in (None, '0'):
            # unset handle or handle '0' is default closed filled arrow
            return ARROWS.closed_filled
        else:
            block_name = get_block_name_by_handle(handle, self.doc)
            return ARROWS.arrow_name(block_name)  # if arrow return standard arrow name else just the block name

    def get_text_style(self) -> str:
        handle = self.get_dxf_attrib('dimtxsty_handle', None)
        if handle:
            return get_text_style_by_handle(handle, self.doc)
        else:
            logging.warning('DIMSTYLE "{}": text style handle not set.'.format(self.dxf.name))
            return 'Standard'

    def set_text_style(self, name: str) -> None:
        style = self.doc.styles.get(name)
        self.set_dxf_attrib('dimtxsty_handle', style.dxf.handle)

    def get_dimblk(self) -> str:
        return self._get_arrow_block_name('dimblk_handle')

    def set_dimblk(self, name) -> None:
        self._set_blk_handle('dimblk_handle', name)

    def get_dimblk1(self) -> str:
        return self._get_arrow_block_name('dimblk1_handle')

    def set_dimblk1(self, name) -> None:
        self._set_blk_handle('dimblk1_handle', name)

    def get_dimblk2(self) -> str:
        return self._get_arrow_block_name('dimblk2_handle')

    def set_dimblk2(self, name) -> None:
        self._set_blk_handle('dimblk2_handle', name)

    def get_dimldrblk(self) -> str:
        return self._get_arrow_block_name('dimldrblk_handle')

    def set_dimldrblk(self, name) -> None:
        self._set_blk_handle('dimldrblk_handle', name)

    def get_ltype_name(self, dimvar: str) -> Optional[str]:
        if self.dxfversion < 'AC1021':
            logger.debug('Linetype support for DIMSTYLE requires DXF R2007 or later.')

        handle = self.get_dxf_attrib(dimvar, None)
        if handle:
            ltype = self.ocrawing.get_dxf_entity(handle)
            return ltype.dxf.name
        else:
            return None

    def get_linetype(self):
        return self.get_ltype_name('dimltype_handle')

    def get_ext1_linetype(self):
        return self.get_ltype_name('dimltex1_handle')

    def get_ext2_linetype(self):
        return self.get_ltype_name('dimltex2_handle')

    def get_ltype_handle(self, linetype_name: str) -> str:
        ltype = self.doc.linetypes.get(linetype_name)
        return ltype.dxf.handle

    def set_linetype(self, name: str) -> None:
        self.dxf.dimltype_handle = self.get_ltype_handle(name)

    def set_ext1_linetype(self, name: str) -> None:
        self.dxf.dimltex1_handle = self.get_ltype_handle(name)

    def set_ext2_linetype(self, name: str) -> None:
        self.dxf.dimltex2_handle = self.get_ltype_handle(name)

    def set_linetypes(self, dimline=None, ext1=None, ext2=None) -> None:
        if self.dxfversion >= 'AC1021':
            if dimline is not None:
                self.set_linetype(dimline)
            if ext1 is not None:
                self.set_ext1_linetype(ext1)
            if ext2 is not None:
                self.set_ext2_linetype(ext2)
        else:
            logger.debug('Linetype support requires DXF R2007 or later.')


def get_text_style_by_handle(handle, doc: 'Drawing', default='STANDARD') -> str:
    try:
        entry = doc.entitydb[handle]
    except DXFKeyError:
        logging.warning('Invalid text style handle "{}".'.format(handle))
        text_style_name = default
    else:
        text_style_name = entry.dxf.name
    return text_style_name


def get_block_name_by_handle(handle, doc: 'Drawing', default='') -> str:
    try:
        entry = doc.entitydb[handle]
    except DXFKeyError:
        block_name = default
    else:
        block_name = entry.dxf.name
    return block_name
