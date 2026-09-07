// Protect the King - 2D. The player controller, and the only thing that decides
// which guard the player is driving.

#include "Core/PTKPlayerController.h"
#include "Core/PTKGameModeBase.h"
#include "UI/PTKStartScreen.h"
#include "InputCoreTypes.h"
#include "InputTriggers.h"

#include "AI/PTKGuardAIController.h"
#include "Characters/PTKGuardCharacter.h"
#include "Components/PTKHealthComponent.h"
#include "Core/PTKTypes.h"
#include "EnhancedInputComponent.h"
#include "EnhancedInputSubsystems.h"
#include "Engine/LocalPlayer.h"
#include "Engine/World.h"
#include "EngineUtils.h"
#include "InputAction.h"
#include "InputMappingContext.h"
#include "ProtectTheKing2D.h"
#include "TimerManager.h"
#include "UObject/ConstructorHelpers.h"

#include UE_INLINE_GENERATED_CPP_BY_NAME(PTKPlayerController)

namespace PTKSwitchDefaults
{
	/** Slot order. The number keys and the death hand-off both read this. */
	static const FName Order[] = {
		TEXT("Ravager"), TEXT("Aegis"), TEXT("Wraith"), TEXT("Reaver"), TEXT("Sentinel")
	};

	static const TCHAR* const ContextPath = TEXT("/Game/PTK/Input/IMC_PTK_GuardSwitch");
	static const TCHAR* const ActionPathFormat = TEXT("/Game/PTK/Input/IA_SelectGuard%d");
}

APTKPlayerController::APTKPlayerController()
{
	for (const FName& Id : PTKSwitchDefaults::Order)
	{
		GuardOrder.Add(Id);
	}

	// Found by path rather than assigned in a Blueprint, so switching works in a
	// fresh clone with no BP_PlayerController asset to forget to set up. Both
	// are still EditDefaultsOnly, so a Blueprint subclass can override them.
	static ConstructorHelpers::FObjectFinder<UInputMappingContext> SwitchContext(
		PTKSwitchDefaults::ContextPath);
	if (SwitchContext.Succeeded())
	{
		SwitchMappingContext = SwitchContext.Object;
	}

	GuardSelectActions.SetNum(UE_ARRAY_COUNT(PTKSwitchDefaults::Order));
	// Loading five assets by index needs five separate static finders: a
	// ConstructorHelpers finder is a static local, so one inside a loop would
	// resolve exactly once and hand back the same action for every slot.
	static ConstructorHelpers::FObjectFinder<UInputAction> Select1(TEXT("/Game/PTK/Input/IA_SelectGuard1"));
	static ConstructorHelpers::FObjectFinder<UInputAction> Select2(TEXT("/Game/PTK/Input/IA_SelectGuard2"));
	static ConstructorHelpers::FObjectFinder<UInputAction> Select3(TEXT("/Game/PTK/Input/IA_SelectGuard3"));
	static ConstructorHelpers::FObjectFinder<UInputAction> Select4(TEXT("/Game/PTK/Input/IA_SelectGuard4"));
	static ConstructorHelpers::FObjectFinder<UInputAction> Select5(TEXT("/Game/PTK/Input/IA_SelectGuard5"));
	const ConstructorHelpers::FObjectFinder<UInputAction>* const Finders[] = {
		&Select1, &Select2, &Select3, &Select4, &Select5
	};
	for (int32 Index = 0; Index < GuardSelectActions.Num(); ++Index)
	{
		if (Finders[Index]->Succeeded())
		{
			GuardSelectActions[Index] = Finders[Index]->Object;
		}
	}
}

void APTKPlayerController::BeginPlay()
{
	Super::BeginPlay();

	AddSwitchMappingContext();
	LogRoster(TEXT("start"));
	if (IsLocalController() && !APTKGameModeBase::IsGameplayActive(GetWorld()))
	{
		StartScreen = CreateWidget<UPTKStartScreen>(this);
		if (StartScreen) StartScreen->AddToViewport(100);
		SetInputMode(FInputModeGameOnly());
	}
	if (StartMappingContext)
	{
		if (UEnhancedInputLocalPlayerSubsystem* Subsystem = ULocalPlayer::GetSubsystem<UEnhancedInputLocalPlayerSubsystem>(GetLocalPlayer()))
		{
			Subsystem->AddMappingContext(StartMappingContext, 2);
		}
	}
}

void APTKPlayerController::SetupInputComponent()
{
	Super::SetupInputComponent();

	UEnhancedInputComponent* const EnhancedInput = Cast<UEnhancedInputComponent>(InputComponent);
	if (!EnhancedInput)
	{
		UE_LOG(LogPTK, Error,
			TEXT("SWITCH | the player controller did not receive a UEnhancedInputComponent - ")
			TEXT("guard switching is disabled. Check DefaultInputComponentClass in Config/DefaultInput.ini."));
		return;
	}

	StartAction = NewObject<UInputAction>(this);
	StartAction->ValueType = EInputActionValueType::Boolean;
	StartAction->Triggers.Add(NewObject<UInputTriggerPressed>(StartAction));
	StartMappingContext = NewObject<UInputMappingContext>(this);
	StartMappingContext->MapKey(StartAction, EKeys::Enter);
	EnhancedInput->BindAction(StartAction, ETriggerEvent::Triggered, this, &APTKPlayerController::Input_StartGame);
	if (UEnhancedInputLocalPlayerSubsystem* Subsystem = ULocalPlayer::GetSubsystem<UEnhancedInputLocalPlayerSubsystem>(GetLocalPlayer()))
	{
		Subsystem->AddMappingContext(StartMappingContext, 2);
	}

	int32 Bound = 0;
	for (int32 Index = 0; Index < GuardSelectActions.Num(); ++Index)
	{
		UInputAction* const Action = GuardSelectActions[Index];
		if (!Action)
		{
			UE_LOG(LogPTK, Warning,
				TEXT("SWITCH | no input action for slot %d - that number key will do nothing. ")
				TEXT("Run Tools/PTK_SetupGuardSwitching.py."), Index + 1);
			continue;
		}
		// Started, not Triggered: one switch per press. The slot travels as a
		// bound payload, which is what lets five keys share one handler instead
		// of five near-identical functions.
		EnhancedInput->BindAction(Action, ETriggerEvent::Started, this,
			&APTKPlayerController::Input_SelectGuard, Index + 1);
		++Bound;
	}

	UE_LOG(LogPTK, Log, TEXT("SWITCH | %d guard-select key(s) bound"), Bound);
}

void APTKPlayerController::AddSwitchMappingContext()
{
	if (!SwitchMappingContext)
	{
		UE_LOG(LogPTK, Warning,
			TEXT("SWITCH | IMC_PTK_GuardSwitch is not assigned - the number keys are unmapped. ")
			TEXT("Run Tools/PTK_SetupGuardSwitching.py."));
		return;
	}

	if (UEnhancedInputLocalPlayerSubsystem* const Subsystem =
			ULocalPlayer::GetSubsystem<UEnhancedInputLocalPlayerSubsystem>(GetLocalPlayer()))
	{
		// On the controller, never on the pawn: this has to outlive every
		// possession change, including the ones it causes itself.
		Subsystem->AddMappingContext(SwitchMappingContext, SwitchMappingPriority);
		UE_LOG(LogPTK, Log, TEXT("SWITCH | %s added at priority %d"),
			*SwitchMappingContext->GetName(), SwitchMappingPriority);
	}
}

// ---------------------------------------------------------------------------
// Possession
// ---------------------------------------------------------------------------
void APTKPlayerController::OnPossess(APawn* InPawn)
{
	Super::OnPossess(InPawn);

	// Listening for the death of whoever is being driven, so the player is
	// handed to the next guard instead of being left holding a corpse.
	if (const APTKGuardCharacter* const Guard = Cast<APTKGuardCharacter>(InPawn))
	{
		if (UPTKHealthComponent* const Health = Guard->GetHealthComponent())
		{
			Health->OnDeath.AddUniqueDynamic(this, &APTKPlayerController::HandlePlayerGuardDeath);
		}
	}

	// Cheap and idempotent. Re-asserted on every possession so that the number
	// keys can never be the casualty of a pawn swap - they are the one control
	// that has to work even when the guard under them does not.
	AddSwitchMappingContext();
}

void APTKPlayerController::OnUnPossess()
{
	if (const APTKGuardCharacter* const Guard = Cast<APTKGuardCharacter>(GetPawn()))
	{
		if (UPTKHealthComponent* const Health = Guard->GetHealthComponent())
		{
			Health->OnDeath.RemoveDynamic(this, &APTKPlayerController::HandlePlayerGuardDeath);
		}
	}
	Super::OnUnPossess();
}

// ---------------------------------------------------------------------------
// The roster
// ---------------------------------------------------------------------------
APTKGuardCharacter* APTKPlayerController::GetGuardInSlot(int32 Slot) const
{
	if (!GuardOrder.IsValidIndex(Slot - 1) || !GetWorld())
	{
		return nullptr;
	}
	const FName Wanted = GuardOrder[Slot - 1];

	// Walked fresh rather than cached. Five guards is nothing next to the swarm
	// this already iterates every frame elsewhere, and a cache would be one more
	// thing that can be stale at exactly the moment a guard dies.
	for (TActorIterator<APTKGuardCharacter> It(GetWorld()); It; ++It)
	{
		if (IsValid(*It) && It->GetGuardId() == Wanted)
		{
			return *It;
		}
	}
	return nullptr;
}

int32 APTKPlayerController::GetSlotOf(const APTKGuardCharacter* Guard) const
{
	if (!Guard)
	{
		return INDEX_NONE;
	}
	const int32 Index = GuardOrder.IndexOfByKey(Guard->GetGuardId());
	return (Index == INDEX_NONE) ? INDEX_NONE : Index + 1;
}

APTKGuardCharacter* APTKPlayerController::GetPlayerGuard() const
{
	return Cast<APTKGuardCharacter>(GetPawn());
}

int32 APTKPlayerController::FindNextLivingSlot(int32 AfterSlot) const
{
	const int32 Count = GuardOrder.Num();
	if (Count <= 0)
	{
		return INDEX_NONE;
	}
	// Starting one past AfterSlot and wrapping exactly once gives the fixed
	// Ravager -> Aegis -> Wraith -> Reaver -> Sentinel order the design asks
	// for, without the hand-off ever picking the guard that just died.
	const int32 Start = (AfterSlot == INDEX_NONE) ? 0 : AfterSlot;
	for (int32 Step = 0; Step < Count; ++Step)
	{
		const int32 Slot = ((Start + Step) % Count) + 1;
		const APTKGuardCharacter* const Guard = GetGuardInSlot(Slot);
		if (Guard && !Guard->IsDead())
		{
			return Slot;
		}
	}
	return INDEX_NONE;
}

// ---------------------------------------------------------------------------
// Switching
// ---------------------------------------------------------------------------
void APTKPlayerController::Input_SelectGuard(int32 Slot)
{
	SelectGuardSlot(Slot);
}

bool APTKPlayerController::SelectGuardSlot(int32 Slot)
{
	if (!APTKGameModeBase::IsGameplayActive(GetWorld())) return false;
	if (!GuardOrder.IsValidIndex(Slot - 1))
	{
		UE_LOG(LogPTK, Warning, TEXT("SWITCH | there is no slot %d"), Slot);
		return false;
	}
	const FName Wanted = GuardOrder[Slot - 1];

	APTKGuardCharacter* const Guard = GetGuardInSlot(Slot);
	if (!Guard)
	{
		UE_LOG(LogPTK, Warning,
			TEXT("SWITCH | cannot switch to %s - that guard is not in the level"), *Wanted.ToString());
		return false;
	}

	if (Guard->IsDead())
	{
		// The whole of the dead-guard rule. Nothing is possessed, nothing is
		// healed, nothing is respawned - the player simply keeps what they have.
		UE_LOG(LogPTK, Warning,
			TEXT("SWITCH | cannot switch to %s - guard is dead"), *Wanted.ToString());
		return false;
	}

	if (Guard == GetPawn())
	{
		UE_LOG(LogPTK, Log,
			TEXT("SWITCH | already playing %s - nothing to do"), *Wanted.ToString());
		return false;
	}

	return TakeControlOf(Guard);
}

bool APTKPlayerController::TakeControlOf(APTKGuardCharacter* Guard)
{
	if (!IsValid(Guard) || Guard->IsDead())
	{
		return false;
	}

	// Captured BEFORE possessing: AController::Possess un-possesses whatever
	// this controller currently holds, so by the time Possess returns there is
	// no way left to ask who the player was driving.
	APTKGuardCharacter* const Previous = Cast<APTKGuardCharacter>(GetPawn());

	// Park the AI that is holding the new guard, and stop it deciding things
	// while it still has the pawn - it will be handed back this same controller
	// when the player leaves, so its defend cooldown carries across.
	if (APTKGuardAIController* const AI = Cast<APTKGuardAIController>(Guard->GetController()))
	{
		AI->SetAIEnabled(false);
		ParkedAI.Add(Guard->GetGuardId(), AI);
	}

	Possess(Guard);

	// Only now, when Previous is guaranteed to be controller-less.
	if (Previous && Previous != Guard)
	{
		ReleaseToAI(Previous);
	}

	// Explicit rather than relying on bAutoManageActiveCameraTarget: the view
	// target is the one part of a switch the player sees immediately, and it is
	// worth one line to make it a fact rather than an engine default.
	SetViewTarget(Guard);

	// Said plainly rather than assumed: a guard the player leaves behind because
	// it just died does NOT return to the AI, and a log that claimed it did
	// would be the first thing to mislead anyone reading a death hand-off.
	UE_LOG(LogPTK, Warning,
		TEXT("SWITCH | player takes %s (slot %d) | %s"),
		*Guard->GetGuardId().ToString(), GetSlotOf(Guard),
		Previous
			? (Previous->IsDead()
				? *FString::Printf(TEXT("%s left dead on the field"),
					*Previous->GetGuardId().ToString())
				: *FString::Printf(TEXT("%s returns to AI"),
					*Previous->GetGuardId().ToString()))
			: TEXT("no guard was being driven"));

	return true;
}

void APTKPlayerController::ReleaseToAI(APTKGuardCharacter* Guard)
{
	if (!IsValid(Guard))
	{
		return;
	}

	// The player may have been holding a movement key at the moment of the
	// switch. The AI overwrites this every tick anyway, but a guard should not
	// take a step it was not told to take on the frame it changes hands.
	Guard->SetMoveInput(FVector2D::ZeroVector);

	if (Guard->IsDead())
	{
		// A corpse needs no AI, and giving it one would put a controller on the
		// field whose only job is to notice it is dead.
		UE_LOG(LogPTK, Log,
			TEXT("SWITCH | %s is dead - left without a controller"), *Guard->GetGuardId().ToString());
		return;
	}

	if (Guard->GetController() != nullptr)
	{
		UE_LOG(LogPTK, Warning,
			TEXT("SWITCH | %s already has controller %s - not adding another"),
			*Guard->GetGuardId().ToString(), *GetNameSafe(Guard->GetController()));
		return;
	}

	APTKGuardAIController* AI = nullptr;
	if (TObjectPtr<APTKGuardAIController>* const Parked = ParkedAI.Find(Guard->GetGuardId()))
	{
		// Re-usable only if it still exists and is not driving something else.
		if (IsValid(*Parked) && (*Parked)->GetPawn() == nullptr)
		{
			AI = *Parked;
			AI->Possess(Guard);
		}
	}

	if (!AI)
	{
		// Nothing parked - the player's starting guard is spawned by the game
		// mode and has never had an AI controller. SpawnDefaultController uses
		// the Blueprint's own AIControllerClass, so this is still the one shared
		// guard AI and not a second system.
		Guard->SpawnDefaultController();
		AI = Cast<APTKGuardAIController>(Guard->GetController());
		if (AI)
		{
			ParkedAI.Add(Guard->GetGuardId(), AI);
		}
	}

	if (!AI)
	{
		UE_LOG(LogPTK, Error,
			TEXT("SWITCH | %s could not be given an AI controller - check that its Blueprint's ")
			TEXT("AIControllerClass is PTKGuardAIController (Tools/PTK_SetupGuardPosts.py)."),
			*Guard->GetGuardId().ToString());
		return;
	}

	AI->SetAIEnabled(true);
	UE_LOG(LogPTK, Log,
		TEXT("SWITCH | %s handed to %s | returning to post (%.0f, %.0f)"),
		*Guard->GetGuardId().ToString(), *AI->GetName(),
		Guard->GetHomePosition().X, Guard->GetHomePosition().Z);
}

// ---------------------------------------------------------------------------
// Death of the guard the player is driving
// ---------------------------------------------------------------------------
void APTKPlayerController::HandlePlayerGuardDeath(UPTKHealthComponent* /*Component*/,
	AActor* /*Killer*/)
{
	const int32 FallenSlot = GetSlotOf(GetPlayerGuard());

	UE_LOG(LogPTK, Warning, TEXT("SWITCH | the played guard has fallen (slot %d)"), FallenSlot);

	// Deferred one tick. OnDeath fires from inside ApplyDamage, which can be
	// half way through a melee sweep or a splash loop over several victims -
	// re-possessing there would tear the input component down underneath code
	// that is still running.
	if (UWorld* const World = GetWorld())
	{
		World->GetTimerManager().SetTimerForNextTick(
			FTimerDelegate::CreateWeakLambda(this, [this, FallenSlot]()
			{
				AutoSwitchAfterDeath(FallenSlot);
			}));
	}
}

void APTKPlayerController::AutoSwitchAfterDeath(int32 FallenSlot)
{
	const int32 Next = FindNextLivingSlot(FallenSlot);
	if (Next == INDEX_NONE)
	{
		// The whole line is down. The dead guard stays possessed deliberately:
		// it is the camera's view target, and un-possessing would drop the view
		// to the controller's own transform. The player watches the last of the
		// fight from where their guard fell, and the King is the loss condition
		// from here - the enemies have already re-targeted him by themselves.
		UE_LOG(LogPTK, Warning,
			TEXT("SWITCH | every guard is down - no living guard to take. The King stands alone."));
		LogRoster(TEXT("all guards dead"));
		return;
	}

	UE_LOG(LogPTK, Warning, TEXT("SWITCH | automatic hand-off: slot %d -> slot %d"),
		FallenSlot, Next);
	TakeControlOf(GetGuardInSlot(Next));
}

// ---------------------------------------------------------------------------
void APTKPlayerController::LogRoster(const FString& Stage) const
{
	// The view target is on this line because "the camera followed" is
	// otherwise the one claim in a switch that nothing in a log can support.
	UE_LOG(LogPTK, Warning, TEXT("ROSTER | %s | view target: %s"),
		*Stage, *GetNameSafe(const_cast<APTKPlayerController*>(this)->GetViewTarget()));
	for (int32 Slot = 1; Slot <= GuardOrder.Num(); ++Slot)
	{
		const APTKGuardCharacter* const Guard = GetGuardInSlot(Slot);
		if (!Guard)
		{
			UE_LOG(LogPTK, Warning, TEXT("ROSTER | %d %-9s absent"),
				Slot, *GuardOrder[Slot - 1].ToString());
			continue;
		}
		const UPTKHealthComponent* const Health = Guard->GetHealthComponent();
		const AController* const Ctrl = Guard->GetController();
		const bool bPlayer = (Guard == GetPawn());
		const FVector Where = Guard->GetActorLocation();
		UE_LOG(LogPTK, Warning,
			TEXT("ROSTER | %d %-9s %-6s HP %7.1f/%7.1f  driver %-8s  pos (%6.0f,%6.0f)  ")
			TEXT("%-6s facing %-5s  controller %s"),
			Slot, *GuardOrder[Slot - 1].ToString(),
			Guard->IsDead() ? TEXT("DEAD") : TEXT("alive"),
			Health ? Health->GetCurrentHealth() : 0.0f,
			Health ? Health->GetMaxHealth() : 0.0f,
			bPlayer ? TEXT("PLAYER") : (Ctrl ? TEXT("AI") : TEXT("none")),
			Where.X, Where.Z,
			*UPTKTypesLibrary::MovementStateToString(Guard->GetMovementState()),
			*UPTKTypesLibrary::DirectionToString(Guard->GetFacingDirection()),
			*GetNameSafe(Ctrl));
	}
}

void APTKPlayerController::Input_StartGame()
{
	if (APTKGameModeBase* Mode = GetWorld()->GetAuthGameMode<APTKGameModeBase>())
	{
		Mode->StartGame();
	}
}

void APTKPlayerController::HideStartScreen()
{
	if (StartScreen)
	{
		StartScreen->RemoveFromParent();
		StartScreen = nullptr;
	}
}
