#pragma once

#include "CoreMinimal.h"
#include "Blueprint/UserWidget.h"
#include "PTKStartScreen.generated.h"

/** Minimal UMG overlay; the controller owns Enter and its lifetime. */
UCLASS()
class PROTECTTHEKING2D_API UPTKStartScreen : public UUserWidget
{
	GENERATED_BODY()

protected:
	virtual void NativeOnInitialized() override;
};
