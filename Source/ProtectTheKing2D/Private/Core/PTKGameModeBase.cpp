// Protect the King - 2D. Base game mode.

#include "Core/PTKGameModeBase.h"
#include "Core/PTKEnemySpawner.h"
#include "Engine/World.h"
#include "EngineUtils.h"

#include "Core/PTKCombatHUD.h"
#include "Core/PTKPlayerController.h"
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

	// Guard switching lives on the controller, not on the pawn, so that the
	// number keys survive the pawn being swapped out from under them. See
	// APTKPlayerController.
	PlayerControllerClass = APTKPlayerController::StaticClass();

	// Ravager is slot 1, and the guard the player starts on. The other four are
	// placed in the level and are AI-driven until a number key says otherwise;
	// this is only the starting point, not the only guard the player gets.
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

bool APTKGameModeBase::IsGameplayActive(const UWorld* World)
{
	const APTKGameModeBase* Mode = World ? World->GetAuthGameMode<APTKGameModeBase>() : nullptr;
	return Mode && Mode->IsPlaying();
}

void APTKGameModeBase::StartGame()
{
	if (bPlaying) return;
	bPlaying = true;
	for (TActorIterator<APTKPlayerController> It(GetWorld()); It; ++It)
	{
		It->HideStartScreen();
	}
	for (TActorIterator<APTKEnemySpawner> It(GetWorld()); It; ++It)
	{
		It->StartSpawning();
	}
	UE_LOG(LogPTK, Log, TEXT("GAME START | Playing"));
}
