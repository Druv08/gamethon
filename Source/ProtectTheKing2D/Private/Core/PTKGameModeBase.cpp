// Protect the King - 2D. Base game mode.

#include "Core/PTKGameModeBase.h"

#include "Core/PTKCombatHUD.h"
#include "GameFramework/Pawn.h"
#include "ProtectTheKing2D.h"
#include "UObject/ConstructorHelpers.h"

#include UE_INLINE_GENERATED_CPP_BY_NAME(PTKGameModeBase)

APTKGameModeBase::APTKGameModeBase()
{
	// Prototype combat readout: health bars and the AI state block. Pure canvas
	// drawing, no widget assets - see APTKCombatHUD. Replaced by the real
	// interface later.
	HUDClass = APTKCombatHUD::StaticClass();

	// Ravager is the Phase 1 test subject. Once the other guards exist this
	// becomes a selection driven by the guard-switching system instead.
	static ConstructorHelpers::FClassFinder<APawn> RavagerBP(
		TEXT("/Game/PTK/Characters/Guards/Ravager/Blueprints/BP_Ravager"));

	if (RavagerBP.Succeeded())
	{
		DefaultPawnClass = RavagerBP.Class;
	}
	else
	{
		// Expected on a fresh clone before the Blueprint has been generated.
		UE_LOG(LogPTK, Warning,
			TEXT("BP_Ravager was not found at /Game/PTK/Characters/Guards/Ravager/Blueprints/BP_Ravager. ")
			TEXT("Run Tools/PTK_GenerateAssets.py, then set DefaultPawnClass."));
	}
}
