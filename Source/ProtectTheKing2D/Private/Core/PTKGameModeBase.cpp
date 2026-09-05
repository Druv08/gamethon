// Protect the King - 2D. Base game mode.

#include "Core/PTKGameModeBase.h"

#include "GameFramework/Pawn.h"
#include "ProtectTheKing2D.h"
#include "UObject/ConstructorHelpers.h"

#include UE_INLINE_GENERATED_CPP_BY_NAME(PTKGameModeBase)

APTKGameModeBase::APTKGameModeBase()
{
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
