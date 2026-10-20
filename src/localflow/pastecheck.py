"""Read only the originally eligible composer to confirm an exact paste."""
from .draftwatch import DraftWatch
from .learning import MAX_SPAN,normalized_text


class PasteCheck(DraftWatch):
    def prepare(self):
        if not self.focused():return False
        from comtypes.gen import UIAutomationClient as UIA
        self.element=self.native.uia.GetFocusedElement()
        if not self.eligible():return False
        self.pattern=self.element.GetCurrentPattern(10014).QueryInterface(UIA.IUIAutomationTextPattern)
        selections=self.pattern.GetSelection()
        if selections.Length!=1:return False
        selected=selections.GetElement(0)
        document=self.pattern.DocumentRange
        initial=normalized_text(document.GetText(MAX_SPAN+1))
        prefix=document.Clone();prefix.MoveEndpointByRange(1,selected,0)
        suffix=document.Clone();suffix.MoveEndpointByRange(0,selected,1)
        before=normalized_text(prefix.GetText(MAX_SPAN+1));after=normalized_text(suffix.GetText(MAX_SPAN+1))
        self.expected_document=before+self.expected+after
        if max(len(initial),len(self.expected_document))>MAX_SPAN or initial==self.expected_document:return False
        return self.focused() and self.eligible()

    def check(self):
        if not self.focused() or not self.eligible():return 'changed'
        current=normalized_text(self.pattern.DocumentRange.GetText(MAX_SPAN+1))
        if not self.focused() or not self.eligible():return 'changed'
        return 'inserted' if current==self.expected_document else 'waiting'

    def close(self):
        self.expected=self.expected_document=''
        super().close()
