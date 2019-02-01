from typing import Any, TYPE_CHECKING, Tuple
from ezdxf.lldxf.const import DXFAttributeError, DIMJUST, DIMTAD
from ezdxf.render.arrows import ARROWS
import logging

logger = logging.getLogger('ezdxf')

if TYPE_CHECKING:
    from ezdxf.eztypes import Dimension, UCS, Drawing, DimStyle


class DimStyleOverride:
    def __init__(self, dimension: 'Dimension', override: dict = None):
        # DimStyle for DXF R2000 and later - local import to avoid import cycle!
        from ezdxf.modern.tableentries import DimStyle
        self._DIMSTYLE_CHECKER = DimStyle
        self.dimension = dimension  # type: Dimension
        dim_style_name = dimension.get_dxf_attrib('dimstyle', 'STANDARD')
        self.dimstyle = self.drawing.dimstyles.get(dim_style_name)  # type: DimStyle
        self.dimstyle_attribs = self.get_dstyle_dict()  # type: dict
        self.update(override or {})

    @property
    def drawing(self) -> 'Drawing':
        return self.dimension.drawing

    @property
    def dxfversion(self) -> str:
        return self.dimension.drawing.dxfversion

    def check_valid_attrib(self, name) -> None:
        if name not in self._DIMSTYLE_CHECKER.DXFATTRIBS:
            raise DXFAttributeError('Invalid DXF attribute "{}" for DIMSTYLE.'.format(name))

    def get_dstyle_dict(self) -> dict:
        return self.dimension.get_acad_dstyle(self.dimstyle)

    def get(self, attribute: str, default: Any = None) -> Any:
        if attribute in self.dimstyle_attribs:
            result = self.dimstyle_attribs[attribute]
        else:
            # Return default value for attributes not supported by DXF R12.
            # This is a hack to use the same algorithm to render DXF R2000 and DXF R12 DIMENSION entities.
            # But the DXF R2000 attributes are not stored in the DXF R12 file!!!
            try:
                result = self.dimstyle.get_dxf_attrib(attribute, default)
            except DXFAttributeError:
                self.check_valid_attrib(attribute)
                # return default value for DXF R12 if valid DXF R2000 attribute
                result = default
        return result

    def update(self, attribs: dict) -> None:
        for key, value in attribs.items():
            self.check_valid_attrib(key)
            self.dimstyle_attribs[key] = value

    def __getitem__(self, item: str) -> Any:
        return self.get(item)

    def __setitem__(self, key: str, value: Any) -> None:
        self.check_valid_attrib(key)
        self.dimstyle_attribs[key] = value

    def __delitem__(self, key: str) -> None:
        self.check_valid_attrib(key)
        try:
            del self.dimstyle_attribs[key]
        except KeyError:  # silent discard
            pass

    def commit(self) -> None:
        """
        Write overwritten DIMSTYLE attributes into XDATA section of the DIMENSION entity.

        """
        def set_arrow_handle(attrib_name, block_name):
            attrib_name += '_handle'
            if block_name in ARROWS:  # create all arrows on demand
                block_name = ARROWS.create_block(blocks, block_name)
            if block_name == '_CLOSEDFILLED':  # special arrow
                handle = '0'  # set special #0 handle for closed filled arrow
            else:
                block = blocks.get(block_name)
                handle = block.block_record_handle
            self.dimstyle_attribs[attrib_name] = handle

        def set_linetype_handle(attrib_name, linetype_name):
            ltype = self.drawing.linetypes.get(linetype_name)
            self.dimstyle_attribs[attrib_name + '_handle'] = ltype.dxf.handle

        if self.drawing.dxfversion > 'AC1009':
            # transform block names into block record handles
            blocks = self.drawing.blocks
            for attrib_name in ('dimblk', 'dimblk1', 'dimblk2', 'dimldrblk'):
                try:
                    block_name = self.dimstyle_attribs.pop(attrib_name)
                except KeyError:
                    pass
                else:
                    set_arrow_handle(attrib_name, block_name)

        if self.drawing.dxfversion >= 'AC1021':
            # transform linetype names into LTYPE entry handles
            for attrib_name in ('dimltype', 'dimltex1', 'dimltex2'):
                try:
                    linetype_name = self.dimstyle_attribs.pop(attrib_name)
                except KeyError:
                    pass
                else:
                    set_linetype_handle(attrib_name, linetype_name)

        self.dimension.set_acad_dstyle(self.dimstyle_attribs, self._DIMSTYLE_CHECKER)

    def set_arrows(self, blk: str = None, blk1: str = None, blk2: str = None, ldrblk: str = None,
                   size: float = None) -> None:
        """
        Set arrows or user defined blocks and disable oblique stroke as tick.

        Args:
            blk: defines both arrows at once as name str or user defined block (name)
            blk1: defines left arrow as name str or as user defined block (name)
            blk2: defines right arrow as name str or as user defined block (name)
            ldrblk: defines leader arrow as name str or as user defined block (name)
            size: arrow size in drawing units

        """

        def set_arrow(dimvar: str, name: str) -> None:
            self.dimstyle_attribs[dimvar] = name

        if size is not None:
            self.dimstyle_attribs['dimasz'] = float(size)
        if blk is not None:
            set_arrow('dimblk', blk)
            self.dimstyle_attribs['dimsah'] = 0
            self.dimstyle_attribs['dimtsz'] = 0.  # use arrows
        if blk1 is not None:
            set_arrow('dimblk1', blk1)
            self.dimstyle_attribs['dimsah'] = 1
            self.dimstyle_attribs['dimtsz'] = 0.  # use arrows
        if blk2 is not None:
            set_arrow('dimblk2', blk2)
            self.dimstyle_attribs['dimsah'] = 1
            self.dimstyle_attribs['dimtsz'] = 0.  # use arrows
        if ldrblk is not None:
            set_arrow('dimldrblk', ldrblk)

    def get_arrow_names(self) -> Tuple[str, str]:
        """
        Get arrows as name strings like 'ARCHTICK'.

        """
        dimtsz = self.get('dimtsz')
        blk1, blk2 = None, None
        if dimtsz == 0.:
            if bool(self.get('dimsah')):
                blk1 = self.get('dimblk1')
                blk2 = self.get('dimblk2')
            else:
                blk = self.get('dimblk')
                blk1 = blk
                blk2 = blk
        return blk1, blk2

    def set_tick(self, size: float = 1) -> None:
        """
        Use oblique stroke as tick, disables arrows.

        Args:
            size: arrow size in daring units

        """
        self.dimstyle_attribs['dimtsz'] = float(size)

    def set_align(self, halign=None, valign=None) -> None:
        """
        Set measurement text alignment, `halign` defines the horizontal alignment, `valign` defines the vertical
        alignment, `above1` and `above2` means above extension line 1 or 2 and aligned with extension line.

        Args:
            halign: `left`, `right` or `center`
            valign: `above`, `center`, `below`, `above1`, `above2`

        """
        if halign:
            self.dimstyle_attribs['dimjust'] = DIMJUST[halign.lower()]

        if valign:
            self.dimstyle_attribs['dimtad'] = DIMTAD[valign.lower()]

    def get_renderer(self, ucs: 'UCS' = None):
        return self.drawing.dimension_renderer.dispatch(self, ucs)

    def render(self, ucs: 'UCS' = None) -> None:
        renderer = self.get_renderer(ucs)
        renderer.render()
        if len(self.dimstyle_attribs):
            self.commit()
