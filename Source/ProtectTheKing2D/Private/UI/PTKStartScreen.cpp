#include "UI/PTKStartScreen.h"

#include "Blueprint/WidgetTree.h"
#include "Components/CanvasPanel.h"
#include "Components/CanvasPanelSlot.h"
#include "Components/TextBlock.h"

void UPTKStartScreen::NativeOnInitialized()
{
	Super::NativeOnInitialized();
	UCanvasPanel* Canvas = WidgetTree->ConstructWidget<UCanvasPanel>();
	WidgetTree->RootWidget = Canvas;

	auto AddLine = [this, Canvas](const TCHAR* Label, float Y, int32 Size)
	{
		UTextBlock* Text = WidgetTree->ConstructWidget<UTextBlock>();
		Text->SetText(FText::FromString(Label));
		FSlateFontInfo Font = Text->GetFont();
		Font.Size = Size;
		Text->SetFont(Font);
		Text->SetColorAndOpacity(FSlateColor(FLinearColor::White));
		Text->SetShadowColorAndOpacity(FLinearColor::Black);
		Text->SetShadowOffset(FVector2D(2.0f, 2.0f));
		UCanvasPanelSlot* Slot = Canvas->AddChildToCanvas(Text);
		Slot->SetAnchors(FAnchors(0.5f, 0.12f));
		Slot->SetAlignment(FVector2D(0.5f, 0.0f));
		Slot->SetAutoSize(true);
		Slot->SetPosition(FVector2D(0.0f, Y));
	};
	AddLine(TEXT("PROTECT THE KING"), 0.0f, 40);
	AddLine(TEXT("PRESS ENTER TO START"), 60.0f, 24);
	SetVisibility(ESlateVisibility::HitTestInvisible);
}
